#!/usr/bin/env python3
"""Latency / throughput probe for the CommandCode endpoint (OpenAI-compatible).

v2 adds usage-aware streaming (exact token counts from the trailing usage block)
and separates TTFT-to-first-reasoning-token from TTFT-to-first-visible-token.

Phases (argv, e.g. `python probe_cc_v2.py models stream_long`):
  models       -> /models transport (DNS/TCP/TLS/TTFB) + confirms the model id exists
  stream_long  -> streaming, ~500-token generation: TTFT split + sustained tok/s
  stream_short -> streaming, tiny answer (real-world latency for a short reply)
  effort       -> stream_long at reasoning_effort low / high
  prefill      -> TTFT vs input size
  tiny/medium  -> non-streaming baselines

Raw records are appended to latency_commandcode.json after every request.
"""
import json
import os
import subprocess
import sys
import time
import uuid

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
ENV = os.path.expanduser("~/.hermes/.env")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "latency_commandcode.json")

BASE = os.environ.get("CC_BASE", "https://api.commandcode.ai/provider/v1")
MODEL = os.environ.get("CC_MODEL", "deepseek/deepseek-v4.1-flash")
SID = str(uuid.uuid4())


def load_env():
    d = {}
    with open(ENV, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


KEY = os.environ.get("CC_KEY") or load_env().get("COMMANDCODE_API_KEY")
RECORDS = json.load(open(OUT)) if os.path.exists(OUT) else []


def rec(**kw):
    RECORDS.append(kw)
    with open(OUT, "w") as fh:
        json.dump(RECORDS, fh, indent=1)


def headers():
    return ["-H", "Authorization: Bearer %s" % KEY,
            "-H", "Content-Type: application/json",
            "-H", "User-Agent: " + UA,
            "-H", "Accept: application/json"]


def sh(args, body=None, timeout=300):
    t0 = time.perf_counter()
    r = subprocess.run(args, input=body, capture_output=True, text=True, timeout=timeout)
    return time.perf_counter() - t0, r.stdout, r.stderr


def post(prompt, max_tokens, extra=None):
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "stream": False}
    if extra:
        payload.update(extra)
    body = json.dumps(payload)
    args = ["curl", "-sS", "-X", "POST", BASE + "/chat/completions"] + headers() + \
        ["--data-binary", "@-", "-w", "\n__META__ %{http_code} %{time_starttransfer} %{time_total}"]
    wall, out, err = sh(args, body)
    meta = out.rsplit("__META__", 1)[-1].strip().split() if "__META__" in out else []
    raw = out.rsplit("\n__META__", 1)[0]
    ttfb = float(meta[1]) if len(meta) > 2 else None
    usage, errtype, text = {}, None, None
    try:
        d = json.loads(raw)
        usage = d.get("usage") or {}
        if "error" in d:
            errtype = str((d["error"] or {}).get("message") or d["error"])[:200]
        else:
            ch = (d.get("choices") or [{}])[0]
            text = (ch.get("message") or {}).get("content")
    except Exception:
        errtype = "unparseable:" + raw[:200]
    return {"wall_ms": round(wall * 1000, 1),
            "ttfb_ms": round(ttfb * 1000, 1) if ttfb else None,
            "code": meta[0] if meta else "?",
            "in_tokens": usage.get("prompt_tokens"),
            "out_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "error": errtype, "text_head": (text or "")[:60],
            "stderr": err.strip()[:150] or None}


def _drain(prompt, max_tokens, extra=None):
    """Run a streaming request; return [(elapsed_s, parsed_chunk), ...] and the end time."""
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "stream": True,
               "stream_options": {"include_usage": True}}
    if extra:
        payload.update(extra)
    args = ["curl", "-sS", "-N", "-X", "POST", BASE + "/chat/completions"] + headers() + \
        ["--data-binary", "@-"]
    t0 = time.perf_counter()
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)
    p.stdin.write(json.dumps(payload))
    p.stdin.close()
    chunks = []
    for raw in p.stdout:
        now = time.perf_counter() - t0
        raw = raw.strip()
        if not raw.startswith("data:"):
            continue
        pay = raw[5:].strip()
        if pay == "[DONE]":
            continue
        try:
            chunks.append((now, json.loads(pay)))
        except Exception:
            chunks.append((now, {"_raw": pay[:200]}))
    p.wait()
    return chunks, (time.perf_counter() - t0)


def stream_parsed(prompt, max_tokens, extra=None):
    chunks, end_s = _drain(prompt, max_tokens, extra)
    first_any = first_reason = first_content = last = None
    n_reason = n_content = n_empty = 0
    usage, errsample = {}, None
    for ts, d in chunks:
        if d.get("_raw") and '"error"' in d["_raw"] and errsample is None:
            errsample = d["_raw"]
        if d.get("usage"):
            usage = d["usage"]
        ch = (d.get("choices") or [{}])[0]
        delta = ch.get("delta") or {}
        if delta.get("reasoning") or delta.get("reasoning_content"):
            if first_any is None:
                first_any = ts
            if first_reason is None:
                first_reason = ts
            n_reason += 1
            last = ts
        elif delta.get("content"):
            if first_any is None:
                first_any = ts
            if first_content is None:
                first_content = ts
            n_content += 1
            last = ts
        else:
            n_empty += 1
    out_tok = usage.get("completion_tokens")
    reason_tok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    content_tok = (out_tok - reason_tok) if (out_tok is not None and reason_tok is not None) else None
    gen_s = (last - first_any) if (last is not None and first_any is not None) else None
    vis_s = (last - first_content) if (last is not None and first_content is not None) else None
    return {
        "ttft_any_ms": round(first_any * 1000, 1) if first_any is not None else None,
        "ttft_reasoning_ms": round(first_reason * 1000, 1) if first_reason is not None else None,
        "ttft_content_ms": round(first_content * 1000, 1) if first_content is not None else None,
        "total_ms": round(end_s * 1000, 1),
        "gen_ms": round(gen_s * 1000, 1) if gen_s else None,
        "in_tokens": usage.get("prompt_tokens"),
        "out_tokens": out_tok,
        "reasoning_tokens": reason_tok,
        "content_tokens": content_tok,
        "deltas_reasoning": n_reason, "deltas_content": n_content, "deltas_empty": n_empty,
        "tok_per_s_total": round(out_tok / gen_s, 1) if (out_tok and gen_s) else None,
        "tok_per_s_visible": round(content_tok / vis_s, 1) if (content_tok and vis_s) else None,
        "error": errsample,
    }


def _show(tag, i, r):
    print("%-14s [%d] ttft_any=%s ttft_reason=%s ttft_content=%s total=%s | in=%s out=%s "
          "(reason=%s content=%s) | tok/s total=%s visible=%s | deltas r/c/e=%s/%s/%s %s"
          % (tag, i, r["ttft_any_ms"], r["ttft_reasoning_ms"], r["ttft_content_ms"], r["total_ms"],
             r["in_tokens"], r["out_tokens"], r["reasoning_tokens"], r["content_tokens"],
             r["tok_per_s_total"], r["tok_per_s_visible"],
             r["deltas_reasoning"], r["deltas_content"], r["deltas_empty"], r["error"] or ""))


def phase_models():
    for i in range(3):
        _, out, err = sh(["curl", "-sS", "-o", "/dev/null", "-H", "Authorization: Bearer %s" % KEY,
                          "-H", "User-Agent: " + UA, "-w",
                          "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} "
                          "%{time_starttransfer} %{time_total}", BASE + "/models"])
        parts = out.split()
        if len(parts) >= 6 and parts[0] == "200":
            r = {"kind": "models", "iter": i + 1, "code": parts[0],
                 "dns_ms": round(float(parts[1]) * 1000, 1), "tcp_ms": round(float(parts[2]) * 1000, 1),
                 "tls_ms": round(float(parts[3]) * 1000, 1), "ttfb_ms": round(float(parts[4]) * 1000, 1),
                 "total_ms": round(float(parts[5]) * 1000, 1)}
        else:
            r = {"kind": "models", "iter": i + 1, "code": parts[0] if parts else "?",
                 "error": (out or err).strip()[:200]}
        rec(**r)
        print("models", r)


def phase_stream_long(n=4):
    for i in range(n):
        r = stream_parsed("List the integers from 1 to 250, one per line, no other text.", 1200)
        rec(kind="stream_long", iter=i + 1, **r)
        _show("stream_long", i + 1, r)


def phase_stream_short(n=6):
    for i in range(n):
        r = stream_parsed("Reply with exactly: pong", 64)
        rec(kind="stream_short", iter=i + 1, **r)
        _show("stream_short", i + 1, r)


def phase_effort(n=2):
    for i in range(n):
        for eff in ("low", "high"):
            r = stream_parsed("List the integers from 1 to 250, one per line, no other text.", 1200,
                              extra={"thinking": {"type": "enabled"}, "reasoning_effort": eff})
            rec(kind="effort_" + eff, iter=i + 1, **r)
            _show("effort_" + eff, i + 1, r)


def phase_prefill():
    for words in (200, 1500, 6000):
        filler = " ".join("token%04d" % i for i in range(words))
        r = stream_parsed(filler + "\n\nReply with exactly: pong", 24,
                          extra={"thinking": {"type": "disabled"}})
        rec(kind="prefill", approx_in_words=words, **r)
        _show("prefill~%d" % words, 1, r)


def phase_tiny(n=4, mx=64):
    for i in range(n):
        r = post("Reply with exactly: pong", mx)
        rec(kind="tiny64", iter=i + 1, **r)
        print("tiny64 [%d] wall=%s ttfb=%s out=%s reason=%s %s"
              % (i + 1, r["wall_ms"], r["ttfb_ms"], r["out_tokens"], r["reasoning_tokens"], r["error"] or ""))


PHASES = {"models": phase_models, "stream_long": phase_stream_long,
          "stream_short": phase_stream_short, "effort": phase_effort,
          "prefill": phase_prefill, "tiny": phase_tiny}

if __name__ == "__main__":
    todo = sys.argv[1:] or ["models"]
    print("key loaded:", bool(KEY), "| base:", BASE, "| model:", MODEL)
    for name in todo:
        print("=== phase:", name, flush=True)
        PHASES[name]()
    print("raw records:", len(RECORDS), "->", OUT)
