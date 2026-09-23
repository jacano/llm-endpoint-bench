#!/usr/bin/env python3
"""Latency / throughput probe for the CommandCode endpoint (OpenAI-compatible).

Phases (pass as argv, e.g. `python probe_commandcode.py models tiny`):
  models  -> /models transport (DNS/TCP/TLS/TTFB) + confirms the model id exists
  tiny    -> non-streaming, 16 max_tokens
  medium  -> non-streaming, "count to 120"
  stream  -> streaming, TTFT + sustained chunk rate
  think   -> streaming with thinking on vs off (deepseek V4 family defaults to thinking)

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


def post(prompt, max_tokens, extra=None, stream=False):
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "stream": stream}
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


def stream_probe(prompt, max_tokens=300, extra=None):
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "stream": True, "stream_options": {"include_usage": True}}
    if extra:
        payload.update(extra)
    body = json.dumps(payload)
    args = ["curl", "-sS", "-N", "-X", "POST", BASE + "/chat/completions"] + headers() + \
        ["--data-binary", "@-"]
    t0 = time.perf_counter()
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)
    p.stdin.write(body)
    p.stdin.close()
    ttft = None
    n = 0
    usage = {}
    sample = None
    marks = []
    for raw in p.stdout:
        now = time.perf_counter()
        if sample is None and '"error"' in raw:
            sample = raw.strip()[:200]
        if raw.startswith("data:") and "[DONE]" not in raw:
            if ttft is None:
                ttft = (now - t0) * 1000
            n += 1
            marks.append(now)
        elif raw.startswith("data:") and "usage" in raw:
            try:
                usage = json.loads(raw[5:].strip()).get("usage") or {}
            except Exception:
                pass
    p.wait()
    total = (marks[-1] - t0) * 1000 if marks else (time.perf_counter() - t0) * 1000
    gen = total - ttft if ttft is not None else None
    # instantaneous rate over the middle 60% (skips warm-up + tail flush)
    inst = None
    if len(marks) > 10:
        lo, hi = marks[int(len(marks) * 0.2)], marks[int(len(marks) * 0.8)]
        inst = round(len(marks) * 0.6 / (hi - lo), 1) if hi > lo else None
    out_tok = usage.get("completion_tokens")
    return {"ttft_ms": round(ttft, 1) if ttft is not None else None,
            "total_ms": round(total, 1),
            "gen_ms": round(gen, 1) if gen else None,
            "chunks": n,
            "chunk_per_s": round(n / (gen / 1000), 1) if gen and n else None,
            "inst_chunk_per_s": inst,
            "out_tokens": out_tok,
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "tok_per_s_decode": round(out_tok / (gen / 1000), 1) if (gen and out_tok) else None,
            "error": sample}


def phase_models():
    for i in range(3):
        _, out, err = sh(["curl", "-sS", "-o", "/dev/null", "-H", "Authorization: Bearer %s" % KEY,
                          "-H", "User-Agent: " + UA, "-w",
                          "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{time_total}",
                          BASE + "/models"])
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
    # authenticated body fetch: confirms auth + model id presence
    _, out, err = sh(["curl", "-sS", BASE + "/models"] + headers())
    try:
        ids = [m["id"] for m in json.loads(out).get("data", [])]
    except Exception:
        ids = None
    print("AUTH /models code-parse ids=%s" % (len(ids) if ids else None))
    if ids:
        print("target present:", MODEL in ids)
        print("deepseek ids:", [i for i in ids if "deepseek" in i.lower()])
        rec(kind="models_body", auth=True, n_ids=len(ids), target_present=MODEL in ids,
            deepseek_ids=[i for i in ids if "deepseek" in i.lower()])
    else:
        print("body head:", out[:300], err[:200])
        rec(kind="models_body", auth=True, error=out[:300])


def phase_tiny(n=6, mx=16):
    for i in range(n):
        r = post("Reply with exactly: pong", mx)
        rec(kind="tiny", iter=i + 1, **r)
        print("tiny [%d] %s ms out=%s %s" % (i + 1, r["wall_ms"], r["out_tokens"], r["error"] or ""))


def phase_medium(n=3, mx=600):
    for i in range(n):
        r = post("Count from 1 to 120, one number per line, no other text.", mx)
        rec(kind="medium", iter=i + 1, **r)
        print("medium [%d] %s ms out=%s %s" % (i + 1, r["wall_ms"], r["out_tokens"], r["error"] or ""))


def phase_stream(n=4):
    for i in range(n):
        r = stream_probe("Count from 1 to 80, one number per line, no other text.")
        rec(kind="stream", iter=i + 1, **r)
        print("stream [%d] %s" % (i + 1, r))


def phase_think(n=2):
    for mode in ("off", "on"):
        for i in range(n):
            extra = {"thinking": {"type": "disabled"}} if mode == "off" else {"thinking": {"type": "enabled"}}
            r = stream_probe("Count from 1 to 80, one number per line, no other text.", extra=extra)
            rec(kind="think_" + mode, iter=i + 1, **r)
            print("think(%s) [%d] %s" % (mode, i + 1, r))


def phase_tps(n=2, mx=1200):
    """Paired non-stream + stream on a long generation, thinking off vs on.

    Non-stream gives exact completion_tokens (usage); stream gives TTFT and the
    chunk arrival profile. chunks x factor -> tokens, so both are comparable.
    """
    prompt = "List the integers from 1 to 250, one per line, no other text."
    for i in range(n):
        for mode in ("off", "on"):
            extra = {"thinking": {"type": "disabled"}} if mode == "off" else {"thinking": {"type": "enabled"}}
            ns = post(prompt, mx, extra=extra)
            rec(kind="tps_nonstream_" + mode, iter=i + 1, **ns)
            st = stream_probe(prompt, mx, extra=extra)
            rec(kind="tps_stream_" + mode, iter=i + 1, **st)
            factor = (ns["out_tokens"] / st["chunks"]) if (ns.get("out_tokens") and st.get("chunks")) else None
            tps = (st["chunks"] * factor / (st["gen_ms"] / 1000)) if (factor and st.get("gen_ms")) else None
            print("tps[%d] think=%s nonstream wall=%s out=%s reasoning=%s | stream ttft=%s gen=%s chunks=%s "
                  "chunk/s=%s | chunk_factor=%s decode_tok/s=%s %s"
                  % (i + 1, mode, ns["wall_ms"], ns["out_tokens"], ns.get("reasoning_tokens"),
                     st["ttft_ms"], st["gen_ms"], st["chunks"], st["chunk_per_s"],
                     round(factor, 3) if factor else None, round(tps, 1) if tps else None,
                     ns["error"] or st["error"] or ""))


def phase_prefill():
    """TTFT vs input size: synthetic long prompt (ASCII filler), thinking off, tiny output."""
    for words in (200, 1500, 6000):
        filler = " ".join("token%04d" % i for i in range(words))
        prompt = filler + "\n\nReply with exactly: pong"
        r = stream_probe(prompt, 24, extra={"thinking": {"type": "disabled"}})
        rec(kind="prefill", approx_in_words=words, **r)
        print("prefill ~%d words ttft=%s ms total=%s chunks=%s %s" % (words, r["ttft_ms"], r["total_ms"],
                                                                     r["chunks"], r["error"] or ""))


PHASES = {"models": phase_models, "tiny": phase_tiny, "medium": phase_medium,
          "stream": phase_stream, "think": phase_think, "tps": phase_tps, "prefill": phase_prefill}

if __name__ == "__main__":
    todo = sys.argv[1:] or ["models"]
    print("key loaded:", bool(KEY), "| base:", BASE, "| model:", MODEL)
    for name in todo:
        print("=== phase:", name, flush=True)
        PHASES[name]()
    print("raw records:", len(RECORDS), "->", OUT)
