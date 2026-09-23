#!/usr/bin/env python3
"""bench.py -- latency / throughput / TPS benchmark for OpenAI-compatible LLM endpoints.

Phases (all timed with curl + a browser UA, so no SDK retry logic hides the tail):

  transport   DNS/TCP/TLS/TTFB on /models, fresh connection, plus three sequential
              requests in one curl invocation (reused socket) -> separates one-time
              handshake cost from per-request gateway overhead
  short       streaming, tiny answer        -> latency a user actually feels on "hi"
  long        streaming, ~600-token answer  -> TTFT split + sustained decode tok/s
  prefill     streaming, ~18k-token input   -> does TTFT grow with the prompt?
  concurrent  N parallel long requests      -> per-request and aggregate throughput

Token counts always come from the response `usage` block -- never from counting SSE
lines (reasoning deltas, empty deltas and merged chunks make line counts lie).

Examples
--------
    python bench.py list
    python bench.py run --endpoint commandcode
    python bench.py run --endpoint opencode-go --phases short,long
    python bench.py ab --a commandcode --b opencode-go          # interleaved A/B
    python bench.py report results/commandcode_20260923T1520Z.json

Any other OpenAI-compatible endpoint:
    python bench.py run --base-url https://api.example.com/v1 --model vendor/model \
        --key-env EXAMPLE_API_KEY --session-header --tag example

Keys are read from the environment, falling back to ~/.hermes/.env (names only are
ever printed). Nothing in this repo contains a credential.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import statistics as st
import subprocess
import sys
import time
import uuid

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
HERMES_ENV = os.path.expanduser("~/.hermes/.env")
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")

PROMPT_SHORT = "Reply with exactly: pong"
PROMPT_LONG = "List the integers from 1 to 250, one per line, no other text."
PREFILL_WORDS = 6000  # ~18k tokens of ASCII filler

#: Known endpoints. `deepseek-v4.1-flash` is the same model on both routes;
#: only the id spelling and the transport differ.
ENDPOINTS = {
    "commandcode": {
        "base_url": "https://api.commandcode.ai/provider/v1",
        "model": "deepseek/deepseek-v4.1-flash",
        "key_env": "COMMANDCODE_API_KEY",
        "session_header": False,
    },
    "opencode-go": {
        "base_url": "https://opencode.ai/zen/go/v1",
        "model": "deepseek-v4.1-flash",
        "key_env": "OPENCODE_GO_API_KEY",
        "session_header": True,  # 400 MissingSessionID without it
    },
}


# --------------------------------------------------------------------------- env

def load_env_file(path: str = HERMES_ENV) -> dict:
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def api_key(name: str) -> str | None:
    return os.environ.get(name) or load_env_file().get(name)


def endpoint(name: str = None, base_url: str = None, model: str = None,
             key_env: str = None, session_header: bool = False) -> dict:
    if name:
        if name not in ENDPOINTS:
            sys.exit("unknown endpoint %r (known: %s)" % (name, ", ".join(ENDPOINTS)))
        ep = dict(ENDPOINTS[name])
        ep["name"] = name
    else:
        if not (base_url and model and key_env):
            sys.exit("--base-url, --model and --key-env are all required for a custom endpoint")
        ep = {"name": base_url, "base_url": base_url, "model": model, "key_env": key_env,
              "session_header": session_header}
    ep.update({k: v for k, v in (("base_url", base_url), ("model", model)) if v})
    ep["key"] = api_key(ep["key_env"])
    return ep


# ---------------------------------------------------------------------- transport

def headers(ep: dict, session_id: str | None = None) -> list[str]:
    h = ["-H", "Authorization: Bearer %s" % (ep["key"] or ""),
         "-H", "Content-Type: application/json",
         "-H", "User-Agent: " + UA,
         "-H", "Accept: application/json"]
    if ep["session_header"]:
        h += ["-H", "x-opencode-session: " + (session_id or str(uuid.uuid4()))]
    return h


def curl(args: list[str], body: str | None = None, timeout: int = 300):
    t0 = time.perf_counter()
    r = subprocess.run(args, input=body, capture_output=True, text=True, timeout=timeout)
    return time.perf_counter() - t0, r.stdout, r.stderr


def transport(ep: dict) -> list[dict]:
    """Fresh-connection /models timings, then a socket-reuse probe."""
    recs = []
    url = ep["base_url"] + "/models"
    for i in range(3):
        args = ["curl", "-sS", "-o", "/dev/null"] + headers(ep) + \
            ["-w", "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} "
                   "%{time_starttransfer} %{time_total}", url]
        _, out, err = curl(args, timeout=60)
        p = out.split()
        if len(p) >= 6 and p[0] == "200":
            recs.append({"kind": "models", "iter": i + 1, "code": p[0],
                         "dns_ms": ms(p[1]), "tcp_ms": ms(p[2]), "tls_ms": ms(p[3]),
                         "ttfb_ms": ms(p[4]), "total_ms": ms(p[5])})
        else:
            recs.append({"kind": "models", "iter": i + 1, "code": p[0] if p else "?",
                         "error": (out or err).strip()[:200]})
    # three sequential requests inside ONE curl -> the socket is reused, so TTFB
    # here is the per-request gateway overhead with no handshake in it.
    # one -o per URL, else curl writes the extra bodies to stdout and the numbers
    # get glued onto them.
    args = ["curl", "-sS"] + ["-o", "/dev/null"] * 3 + headers(ep) + \
        ["-w", "%{time_starttransfer}\n", url, url, url]
    _, out, _ = curl(args, timeout=90)
    reuses = [ms(x) for x in out.split() if _is_number(x)]
    for i, t in enumerate(reuses):
        recs.append({"kind": "models_reuse", "iter": i + 1, "ttfb_ms": t})
    return recs


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def ms(seconds: str) -> float:
    return round(float(seconds) * 1000, 1)


# ----------------------------------------------------------------------- streaming

def stream(ep: dict, prompt: str, max_tokens: int) -> dict:
    """Streaming request; TTFT split + exact token counts from the trailing usage block."""
    payload = json.dumps({"model": ep["model"], "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens, "stream": True,
                          "stream_options": {"include_usage": True}})
    args = ["curl", "-sS", "-N", "-X", "POST", ep["base_url"] + "/chat/completions"] + \
        headers(ep) + ["--data-binary", "@-"]
    t0 = time.perf_counter()
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)
    proc.stdin.write(payload)
    proc.stdin.close()
    first_any = first_reason = first_content = last = None
    n_reason = n_content = n_empty = 0
    usage, errsample = {}, None
    for raw in proc.stdout:
        now = time.perf_counter() - t0
        raw = raw.strip()
        if not raw.startswith("data:"):
            continue
        body = raw[5:].strip()
        if body == "[DONE]":
            continue
        if '"error"' in body and errsample is None:
            errsample = body[:200]
        try:
            chunk = json.loads(body)
        except Exception:
            continue
        if chunk.get("usage"):
            usage = chunk["usage"]
        delta = ((chunk.get("choices") or [{}])[0].get("delta")) or {}
        if delta.get("reasoning") or delta.get("reasoning_content"):
            first_any = now if first_any is None else first_any
            first_reason = now if first_reason is None else first_reason
            n_reason += 1
            last = now
        elif delta.get("content"):
            first_any = now if first_any is None else first_any
            first_content = now if first_content is None else first_content
            n_content += 1
            last = now
        else:
            n_empty += 1
    proc.wait()
    end = time.perf_counter() - t0
    out_tok = usage.get("completion_tokens")
    reason_tok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    content_tok = out_tok - reason_tok if (out_tok is not None and reason_tok is not None) else None
    gen = (last - first_any) if (last is not None and first_any is not None) else None
    vis = (last - first_content) if (last is not None and first_content is not None) else None
    return {
        "ttft_any_ms": round(first_any * 1000, 1) if first_any is not None else None,
        "ttft_reasoning_ms": round(first_reason * 1000, 1) if first_reason is not None else None,
        "ttft_content_ms": round(first_content * 1000, 1) if first_content is not None else None,
        "total_ms": round(end * 1000, 1),
        "gen_ms": round(gen * 1000, 1) if gen else None,
        "in_tokens": usage.get("prompt_tokens"),
        "out_tokens": out_tok,
        "reasoning_tokens": reason_tok,
        "content_tokens": content_tok,
        "deltas_reasoning": n_reason, "deltas_content": n_content, "deltas_empty": n_empty,
        "tok_per_s_total": round(out_tok / gen, 1) if (out_tok and gen) else None,
        "tok_per_s_visible": round(content_tok / vis, 1) if (content_tok and vis) else None,
        "error": errsample,
    }


def phase_transport(ep, n_concurrent):
    return transport(ep)


def phase_short(ep, n_concurrent, n=5):
    return [dict(kind="short", iter=i + 1, **stream(ep, PROMPT_SHORT, 64)) for i in range(n)]


def phase_long(ep, n_concurrent, n=4):
    return [dict(kind="long", iter=i + 1, **stream(ep, PROMPT_LONG, 1200)) for i in range(n)]


def phase_prefill(ep, n_concurrent):
    filler = " ".join("token%04d" % i for i in range(PREFILL_WORDS))
    r = stream(ep, filler + "\n\nReply with exactly: pong", 24)
    return [dict(kind="prefill", iter=1, approx_in_tokens=PREFILL_WORDS, **r)]


def phase_concurrent(ep, n_concurrent):
    def one(i):
        return dict(kind="concurrent_%d" % n_concurrent, iter=i + 1,
                    **stream(ep, PROMPT_LONG, 1200))

    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=n_concurrent) as ex:
        rows = list(ex.map(one, range(n_concurrent)))
    wall = time.perf_counter() - t0
    tokens = sum(r.get("out_tokens") or 0 for r in rows)
    rows.append({"kind": "concurrent_summary", "iter": n_concurrent, "n": n_concurrent,
                 "wall_s": round(wall, 3), "out_tokens": tokens,
                 "aggregate_tok_per_s": round(tokens / wall, 1),
                 "request_per_s": round(n_concurrent / wall, 3)})
    return rows


PHASES = {"transport": phase_transport, "short": phase_short, "long": phase_long,
          "prefill": phase_prefill, "concurrent": phase_concurrent}


# ------------------------------------------------------------------------- running

def run_phases(ep: dict, phases: list[str], n_concurrent: int, quiet: bool = False) -> list[dict]:
    recs = []
    for name in phases:
        rows = PHASES[name](ep, n_concurrent)
        for r in rows:
            r.update({"endpoint": ep["name"], "model": ep["model"]})
            print("  %-16s %-12s %s" % (ep["name"], name, summarize(r)), flush=True)
        recs += rows
    return recs


def summarize(r: dict) -> str:
    if r.get("error"):
        return "ERROR " + str(r["error"])[:120]
    if r["kind"] in ("models", "models_reuse"):
        return "code=%s tls=%s ttfb=%s" % (r.get("code", "-"), r.get("tls_ms", "-"), r.get("ttfb_ms", "-"))
    if r["kind"] == "concurrent_summary":
        return "aggregate=%.1f tok/s %.2f req/s" % (r["aggregate_tok_per_s"], r["request_per_s"])
    return ("ttft_any=%s ttft_content=%s total=%s out=%s reason=%s tok/s=%s"
            % (r.get("ttft_any_ms"), r.get("ttft_content_ms"), r.get("total_ms"),
               r.get("out_tokens"), r.get("reasoning_tokens"), r.get("tok_per_s_total")))


def write_results(recs: list[dict], ep: dict, phases: list[str]) -> str:
    os.makedirs(RESULTS, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    tag = "".join(c if c.isalnum() or c in "-_." else "_" for c in ep["name"])
    path = os.path.join(RESULTS, "%s_%s.json" % (tag, stamp))
    payload = {"meta": {"endpoint": ep["name"], "base_url": ep["base_url"], "model": ep["model"],
                        "phases": phases, "started_utc": stamp, "host": os.uname().nodename,
                        "runner": "bench.py"},
               "records": recs}
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=1)
    return path


# ------------------------------------------------------------------------- reports

def load_records(path: str) -> list[dict]:
    data = json.load(open(path))
    if isinstance(data, dict):
        return data.get("records", [])
    return data  # bare list, e.g. the raw session dumps in results/


def med(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(st.median(vals), 1) if vals else None


def report(path: str) -> None:
    recs = load_records(path)
    clean = [r for r in recs if not r.get("error")]
    print("%s: %d records (%d clean)" % (path, len(recs), len(clean)))
    kinds = sorted({r.get("kind") for r in clean})
    metrics = {
        "models": ["dns_ms", "tcp_ms", "tls_ms", "ttfb_ms"],
        "models_reuse": ["ttfb_ms"],
    }
    for k in kinds:
        rows = [r for r in clean if r["kind"] == k]
        if k in metrics:
            keys = metrics[k]
        elif k.startswith("concurrent") and k != "concurrent_summary":
            keys = ["ttft_any_ms", "ttft_content_ms", "total_ms", "out_tokens",
                    "reasoning_tokens", "tok_per_s_total"]
        elif k == "concurrent_summary":
            print("  concurrent_summary: %s" % {m: rows[0].get(m) for m in
                                                ("n", "wall_s", "out_tokens", "aggregate_tok_per_s", "request_per_s") if m in rows[0]})
            continue
        else:
            keys = ["ttft_any_ms", "ttft_content_ms", "total_ms", "in_tokens", "out_tokens",
                    "reasoning_tokens", "content_tokens", "tok_per_s_total", "tok_per_s_visible"]
        print("  %-18s n=%d" % (k, len(rows)))
        for key in keys:
            vals = [r.get(key) for r in rows]
            m = med(vals)
            if m is None:
                continue
            nums = [v for v in vals if isinstance(v, (int, float))]
            print("      %-18s median %-9s min %-9s max %-9s" % (key, m, round(min(nums), 1), round(max(nums), 1)))


# ---------------------------------------------------------------------------- ab

def cmd_ab(args) -> None:
    a, b = endpoint(args.a), endpoint(args.b)
    for ep in (a, b):
        if not ep["key"]:
            sys.exit("no key for %s (env %s)" % (ep["name"], ep["key_env"]))
    phases = args.phases.split(",")
    out = {a["name"]: [], b["name"]: []}
    for phase in phases:
        n = args.n if phase in ("short", "long") else 1
        for i in range(n):
            for ep in (a, b):  # interleaved: provider load hits both sides equally
                rows = PHASES[phase](ep, args.concurrent)
                for r in rows:
                    r.update({"endpoint": ep["name"], "model": ep["model"]})
                    print("  %-14s %-10s [%d] %s" % (ep["name"], phase, i + 1, summarize(r)), flush=True)
                out[ep["name"]] += rows
    for ep in (a, b):
        path = write_results(out[ep["name"]], ep, phases)
        print("wrote", path)


def cmd_run(args) -> None:
    ep = endpoint(args.endpoint, args.base_url, args.model, args.key_env, args.session_header)
    if args.tag:
        ep["name"] = args.tag
    if not ep["key"]:
        sys.exit("no API key for %s: set %s in the environment or ~/.hermes/.env"
                 % (ep["name"], ep["key_env"]))
    phases = args.phases.split(",")
    print("endpoint=%s model=%s phases=%s" % (ep["name"], ep["model"], phases))
    recs = run_phases(ep, phases, args.concurrent)
    path = write_results(recs, ep, phases)
    print("wrote", path)
    report(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show known endpoints")

    r = sub.add_parser("run", help="benchmark one endpoint")
    r.add_argument("--endpoint", choices=sorted(ENDPOINTS))
    r.add_argument("--base-url")
    r.add_argument("--model")
    r.add_argument("--key-env")
    r.add_argument("--session-header", action="store_true",
                   help="send x-opencode-session (OpenCode Go requires it)")
    r.add_argument("--tag", help="name for the results file")
    r.add_argument("--phases", default="transport,short,long,prefill",
                   help="csv of: %s" % ",".join(PHASES))
    r.add_argument("--concurrent", type=int, default=4, help="parallel requests for `concurrent`")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("ab", help="interleaved A/B between two endpoints")
    a.add_argument("--a", required=True, choices=sorted(ENDPOINTS))
    a.add_argument("--b", required=True, choices=sorted(ENDPOINTS))
    a.add_argument("--phases", default="transport,short,long")
    a.add_argument("--n", type=int, default=4, help="rounds for short/long")
    a.add_argument("--concurrent", type=int, default=4)
    a.set_defaults(func=cmd_ab)

    p = sub.add_parser("report", help="aggregate a results file")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=lambda args: [report(f) for f in args.files])

    args = ap.parse_args()
    if args.cmd == "list":
        for name, cfg in ENDPOINTS.items():
            print("%-14s %-45s model=%s key=%s%s" % (
                name, cfg["base_url"], cfg["model"], cfg["key_env"],
                "  (+ x-opencode-session)" if cfg["session_header"] else ""))
        return
    args.func(args)


if __name__ == "__main__":
    main()
