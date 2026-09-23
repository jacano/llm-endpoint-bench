#!/usr/bin/env python3
"""bench.py -- latency / throughput / TPS benchmark for OpenAI-compatible LLM endpoints.

Phases (all timed with curl + a browser UA, so no SDK retry logic hides the tail):

  transport   DNS/TCP/TLS/TTFB on /models, fresh connection, plus three sequential
              requests in one curl invocation (reused socket) -> separates one-time
              handshake cost from per-request gateway overhead; one more request
              reads the body of /models, to confirm the model id of the route
  short       streaming, tiny answer        -> latency a user actually feels on "hi"
  long        streaming, ~600-token answer  -> TTFT split + sustained decode tok/s
  prefill     streaming, ~18k-token input   -> does TTFT grow with the prompt?
  thinking    streaming, ~400-token answer under each reasoning control (the
              toggle `thinking` and the parameter `reasoning_effort`) -> does the
              route honour any of them, or does the model always reason first?
  concurrent  N parallel long requests      -> per-request and aggregate throughput

Token counts come from the response `usage` block.

Examples
--------
    python bench.py list
    python bench.py run --endpoint commandcode
    python bench.py run --endpoint opencode-go --phases short,long
    python bench.py ab --a commandcode --b opencode-go          # interleaved A/B
    python bench.py report results/2026-09-23T150937Z/ab_opencode-go_20260923.json
    python bench.py compare results/2026-09-23T153444Z/ab_commandcode_20260923T153444Z.json \
        results/2026-09-23T153444Z/ab_opencode-go_20260923T153444Z.json

Each run writes its files into a new directory `results/<date>T<time>Z/`, the time of the run in
UTC, so a second run of the same day cannot mix with the first one. The name of the directory
holds no other fact: the host and the operating system are in the `meta` block of each file.
Give --out-dir to put the files of several commands in one directory of a campaign, as in
results/2026-09-23T153444Z/. The name of a file
is <endpoint>_<UTC>.json, and ab_<endpoint>_<UTC>.json for a side of an A/B test: the time of
the run stays in the name of the file and in its `meta` block. The commands `report` and
`compare` print that time, and both accept a directory: `report` on a directory reports every
file of it, and `compare` on a directory compares the two sides of the last run in it. See
results/README.md for the layout of a campaign directory.

Any other OpenAI-compatible endpoint:
    python bench.py run --base-url https://api.example.com/v1 --model vendor/model \
        --key-env EXAMPLE_API_KEY --session-header --tag example

Keys are read from the environment, falling back to ~/.hermes/.env and, on Windows,
to %LOCALAPPDATA%/hermes/.env (names only are ever printed). Nothing in this repo
contains a credential.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import platform
import re
import statistics as st
import subprocess
import sys
import time
import uuid

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
#: Where the keys may live. The first file that exists wins; names only are printed.
ENV_FILES = [
    os.path.expanduser("~/.hermes/.env"),
    # Hermes Agent on Windows keeps its profile under LOCALAPPDATA.
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", ".env"),
]
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
#: curl is a native program: on Windows it reads `NUL`, not the MSYS mount `/dev/null`.
NULL = "NUL" if os.name == "nt" else "/dev/null"


def default_out_dir() -> str:
    """The directory of this run: results/<date>T<time>Z/.

    The time in the name keeps the files of two runs apart, so a second run of
    the same day cannot mix with the first one. The name holds no other fact:
    the host, the operating system and the endpoint are in the `meta` block of
    each file. Give --out-dir to put the files of more than one command in one
    directory of a campaign.
    """
    return os.path.join(RESULTS, time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime()))

PROMPT_SHORT = "Reply with exactly: pong"
PROMPT_LONG = "List the integers from 1 to 250, one per line, no other text."
PREFILL_WORDS = 6000  # ~18k tokens of ASCII filler
#: Below this number of tokens in the numerator, a rate is noise and is not reported:
#: `tok_per_s_total` over the output tokens, `tok_per_s_visible` over the content ones.
MIN_RATE_TOKENS = 10
#: The numerator of each rate, with the words for it: `tok_per_s_visible` divides by the
#: window of the content, `tok_per_s_total` by the window of the whole answer.
RATE_OF = {"tok_per_s_visible": ("content_tokens", "content tokens"),
           "tok_per_s_total": ("out_tokens", "output tokens")}
#: The reasoning controls of the gateway, for the phase `thinking`. The README says
#: that the route ignores all of them.
THINKING_MODES = [
    ("absent", {}),
    ("disabled", {"thinking": {"type": "disabled"}}),
    ("enabled", {"thinking": {"type": "enabled"}}),
    ("effort_low", {"reasoning_effort": "low"}),
    ("effort_high", {"reasoning_effort": "high"}),
]
THINKING_MAX_TOKENS = 400

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

def load_env_file(path: str | None = None) -> dict:
    out = {}
    paths = [path] if path else ENV_FILES
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
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


def curl(args: list[str], body: str | None = None, timeout: int = 300) -> tuple[str, str]:
    """Run curl and return (stdout, stderr). The phases take their own timings."""
    r = subprocess.run(args, input=body, capture_output=True, text=True, timeout=timeout)
    return r.stdout, r.stderr


def transport(ep: dict) -> list[dict]:
    """Fresh-connection /models timings, a socket-reuse probe, and the model id of the route."""
    recs = []
    url = ep["base_url"] + "/models"
    for i in range(3):
        args = ["curl", "-sS", "-o", NULL] + headers(ep) + \
            ["-w", "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} "
                   "%{time_starttransfer} %{time_total}", url]
        out, err = curl(args, timeout=60)
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
    args = ["curl", "-sS"] + ["-o", NULL] * 3 + headers(ep) + \
        ["-w", "%{time_starttransfer}\n", url, url, url]
    out, _ = curl(args, timeout=90)
    reuses = [ms(x) for x in out.split() if _is_number(x)]
    for i, t in enumerate(reuses):
        recs.append({"kind": "models_reuse", "iter": i + 1, "ttfb_ms": t})
    # the body of /models names the model ids of the route: one request, and a
    # results file says whether the model of this endpoint exists on this route.
    out, err = curl(["curl", "-sS", url] + headers(ep), timeout=60)
    try:
        ids = [m.get("id") for m in json.loads(out).get("data", [])]
    except Exception:
        ids = None
    recs.append({"kind": "models_body", "iter": 1,
                 "n_ids": len(ids) if ids else None,
                 "target_present": ep["model"] in ids if ids else None,
                 "error": None if ids else (out or err).strip()[:200]})
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

def stream(ep: dict, prompt: str, max_tokens: int, extra: dict | None = None) -> dict:
    """Streaming request; TTFT split + exact token counts from the trailing usage block."""
    body = {"model": ep["model"], "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "stream": True,
            "stream_options": {"include_usage": True}}
    body.update(extra or {})  # a reasoning control, for the phase `thinking`
    payload = json.dumps(body)
    args = ["curl", "-sS", "-N", "-X", "POST", ep["base_url"] + "/chat/completions"] + \
        headers(ep) + ["--data-binary", "@-"]
    t0 = time.perf_counter()
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)
    proc.stdin.write(payload)
    proc.stdin.close()
    first_any = first_reason = first_content = last = None
    n_unparseable = 0
    usage, errsample = {}, None
    for raw in proc.stdout:
        now = time.perf_counter() - t0
        raw = raw.strip()
        if not raw.startswith("data:"):
            continue
        body_line = raw[5:].strip()
        if body_line == "[DONE]":
            continue
        if '"error"' in body_line and errsample is None:
            errsample = body_line[:200]
        try:
            chunk = json.loads(body_line)
        except Exception:
            n_unparseable += 1
            continue
        if chunk.get("usage"):
            usage = chunk["usage"]
        delta = ((chunk.get("choices") or [{}])[0].get("delta")) or {}
        if delta.get("reasoning") or delta.get("reasoning_content"):
            first_any = now if first_any is None else first_any
            first_reason = now if first_reason is None else first_reason
            last = now
        elif delta.get("content"):
            first_any = now if first_any is None else first_any
            first_content = now if first_content is None else first_content
            last = now
    proc.wait()
    if n_unparseable and errsample is None:
        errsample = "%d lines of the stream did not parse as JSON" % n_unparseable
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
    r = stream(ep, filler + "\n\nReply with exactly: pong", 24, extra={"thinking": {"type": "disabled"}})
    return [dict(kind="prefill", iter=1, approx_in_tokens=PREFILL_WORDS, **r)]


def phase_thinking(ep, n_concurrent):
    """One long answer under each reasoning control -> does the route honour any of them?"""
    rows = []
    for i, (mode, extra) in enumerate(THINKING_MODES):
        r = stream(ep, PROMPT_LONG, THINKING_MAX_TOKENS, extra=extra)
        rows.append(dict(kind="thinking_" + mode, iter=i + 1, mode=mode, **r))
    return rows


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
          "prefill": phase_prefill, "thinking": phase_thinking,
          "concurrent": phase_concurrent}


# ------------------------------------------------------------------------- running

def run_phases(ep: dict, phases: list[str], n_concurrent: int) -> list[dict]:
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
    if r["kind"] == "models_body":
        return "n_ids=%s target_present=%s" % (r.get("n_ids"), r.get("target_present"))
    if r["kind"] == "concurrent_summary":
        return "aggregate=%.1f tok/s %.2f req/s" % (r["aggregate_tok_per_s"], r["request_per_s"])
    return ("%sttft_any=%s ttft_content=%s total=%s out=%s reason=%s tok/s=%s"
            % ("%-9s " % r["mode"] if r.get("mode") else "",
               r.get("ttft_any_ms"), r.get("ttft_content_ms"), r.get("total_ms"),
               r.get("out_tokens"), r.get("reasoning_tokens"), r.get("tok_per_s_total")))


def write_results(recs: list[dict], ep: dict, phases: list[str], out_dir: str | None = None,
                  prefix: str = "") -> str:
    out_dir = out_dir or RESULTS
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    tag = prefix + "".join(c if c.isalnum() or c in "-_." else "_" for c in ep["name"])
    path = os.path.join(out_dir, "%s_%s.json" % (tag, stamp))
    payload = {"meta": {"endpoint": ep["name"], "base_url": ep["base_url"], "model": ep["model"],
                        "phases": phases, "started_utc": stamp, "host": platform.node(),
                        "platform": platform.platform(), "python": platform.python_version(),
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


def load_meta(path: str) -> dict:
    data = json.load(open(path))
    return (data.get("meta") or {}) if isinstance(data, dict) else {}


def generation_line(path: str) -> str:
    """When and where a file was written. A file of a session before bench.py holds no meta."""
    m = load_meta(path)
    if not m:
        return "no meta block: the file records no time of the run"
    return "generated %s on %s | endpoint %s | model %s | phases %s" % (
        m.get("started_utc", "?"), m.get("host", "?"), m.get("endpoint", "?"),
        m.get("model", "?"), ",".join(m.get("phases") or []))


#: The stamp that the tool puts at the end of a file name.
STAMP = re.compile(r"^(\d{8}(?:T\d{6}Z)?)$")


def tag_and_stamp(name: str) -> tuple[str | None, str | None]:
    """Split `ab_commandcode_20260923T153444Z.json` into its tag and its stamp."""
    stem = name[:-5] if name.endswith(".json") else name
    head, _, tail = stem.rpartition("_")
    if head and STAMP.match(tail):
        return head, tail
    return None, None


def dir_pair(directory: str) -> tuple[str, str]:
    """The newest result file of each tag in a directory: the pair of the last run."""
    if not os.path.isdir(directory):
        sys.exit("compare: %s is not a directory" % directory)
    tags: dict[str, list] = {}
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        tag, stamp = tag_and_stamp(name)
        if tag:
            tags.setdefault(tag, []).append((stamp, os.path.join(directory, name)))
    if len(tags) != 2:
        sys.exit("compare: %s holds %d tag(s) (%s). Name the two files of the pair."
                 % (directory, len(tags), ", ".join(sorted(tags)) or "none"))
    pair = [max(rows)[1] for _, rows in sorted(tags.items())]
    return pair[0], pair[1]


def med(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(st.median(vals), 1) if vals else None


def thin_answer(key: str, *rowsets: list[dict]) -> str | None:
    """The words of the numerator when a rate rests on too few tokens, else None.

    Every rowset given must hold enough tokens: a rate that one side of a comparison
    cannot support is not a rate for either side.
    """
    if key not in RATE_OF:
        return None
    field, words = RATE_OF[key]
    counts = [med([r.get(field) for r in rows]) for rows in rowsets if rows]
    counts = [c for c in counts if c is not None]
    return words if (counts and min(counts) < MIN_RATE_TOKENS) else None


def report(path: str) -> None:
    recs = load_records(path)
    clean = [r for r in recs if not r.get("error")]
    print("%s: %d records (%d clean)" % (path, len(recs), len(clean)))
    print("  " + generation_line(path))
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
        elif k == "models_body":
            print("  models_body: %s" % {m: rows[0].get(m) for m in ("n_ids", "target_present")
                                         if m in rows[0]})
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
            words = thin_answer(key, rows)
            if words:
                # a rate over two or three tokens is a large number without meaning
                print("      %-18s skipped: the answer holds fewer than %d %s"
                      % (key, MIN_RATE_TOKENS, words))
                continue
            nums = [v for v in vals if isinstance(v, (int, float))]
            print("      %-18s median %-9s min %-9s max %-9s" % (key, m, round(min(nums), 1), round(max(nums), 1)))


# ----------------------------------------------------------------- comparison

#: Metrics where a low value is better. Every other metric is a rate.
LOWER_IS_BETTER = {"dns_ms", "tcp_ms", "tls_ms", "ttfb_ms", "total_ms", "wall_s",
                   "ttft_any_ms", "ttft_content_ms"}
#: A difference below this fraction is noise (see Limits in the README).
NOISE = 0.10

COMPARE_METRICS = {
    "models": ["dns_ms", "tcp_ms", "tls_ms", "ttfb_ms", "total_ms"],
    "models_reuse": ["ttfb_ms"],
    "models_body": ["n_ids"],
    "concurrent_summary": ["wall_s", "out_tokens", "aggregate_tok_per_s", "request_per_s"],
}
COMPARE_DEFAULT = ["ttft_any_ms", "ttft_content_ms", "total_ms", "in_tokens", "out_tokens",
                   "reasoning_tokens", "content_tokens", "tok_per_s_total", "tok_per_s_visible"]
#: Metrics that are counts, not scores. The tool names no winner for them: more output
#: tokens is not a better result, and a shorter wall clock with fewer tokens is not either.
NO_VERDICT = {"in_tokens", "out_tokens", "reasoning_tokens", "content_tokens", "wall_s"}


def metrics_for(kind: str) -> list[str]:
    return COMPARE_METRICS.get(kind, COMPARE_DEFAULT)


def compare(path_a: str, path_b: str, label_a: str | None = None, label_b: str | None = None,
            kinds: list[str] | None = None) -> None:
    """Print a markdown table of the median of each metric of two result files."""
    ra = [r for r in load_records(path_a) if not r.get("error")]
    rb = [r for r in load_records(path_b) if not r.get("error")]
    la = str(label_a or (ra[0].get("endpoint") if ra else "A"))
    lb = str(label_b or (rb[0].get("endpoint") if rb else "B"))
    ks = kinds or sorted({str(r.get("kind")) for r in ra + rb if r.get("kind")})
    print("%s (%d records)" % (path_a, len(ra)))
    print("  " + generation_line(path_a))
    print("%s (%d records)" % (path_b, len(rb)))
    print("  " + generation_line(path_b))
    print("")
    print("| Kind | Metric | %s | %s | %s / %s | Better |" % (la, lb, lb, la))
    print("|---|---|---|---|---|---|")
    hidden = {}
    for kind in ks:
        rows_a = [r for r in ra if r.get("kind") == kind]
        rows_b = [r for r in rb if r.get("kind") == kind]
        if not rows_a and not rows_b:
            continue
        for key in metrics_for(kind):
            a = med([r.get(key) for r in rows_a])
            b = med([r.get(key) for r in rows_b])
            if a is None and b is None:
                continue
            words = thin_answer(key, rows_a, rows_b)
            if words:
                hidden.setdefault(key, [set(), words])[0].add(kind)
                continue
            ratio = round(b / a, 2) if (a and b) else None
            print("| %s | %s | %s | %s | %s | %s |" % (kind, key, fmt(a), fmt(b), fmt(ratio),
                                                       verdict(key, a, b, la, lb)))
    for key in sorted(hidden):
        kinds_hidden, words = hidden[key]
        print("")
        print("`%s` is not shown for %s: the median answer of the phase holds fewer than "
              "%d %s." % (key, ", ".join(sorted(kinds_hidden)), MIN_RATE_TOKENS, words))
    print("")
    print("The column `%s / %s` is the value of %s divided by the value of %s. "
          "A difference below %d percent shows `same`. The column `Better` stays empty for a "
          "count, because a count is not a score." % (lb, la, lb, la, NOISE * 100))


def verdict(key: str, a, b, label_a: str = "A", label_b: str = "B") -> str:
    if key in NO_VERDICT or a is None or b is None or not a or not b:
        return "-"
    if abs(b / a - 1) < NOISE:
        return "same"
    if key in LOWER_IS_BETTER:
        return label_a if a < b else label_b
    return label_a if a > b else label_b


def fmt(v) -> str:
    return "-" if v is None else ("%g" % v)


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
        path = write_results(out[ep["name"]], ep, phases, args.out_dir or default_out_dir(),
                             prefix="ab_")
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
    path = write_results(recs, ep, phases, args.out_dir or default_out_dir())
    print("wrote", path)
    report(path)


def cmd_report(args) -> None:
    """Print the report of each file that you name, or of each file of a directory."""
    for path in args.files:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if name.endswith(".json"):
                    report(os.path.join(path, name))
        else:
            report(path)


def cmd_compare(args) -> None:
    """Compare two files, or the two sides of the last run in one directory."""
    a, b = (args.a, args.b) if args.b else dir_pair(args.a)
    compare(a, b, args.label_a, args.label_b,
            args.kinds.split(",") if args.kinds else None)


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
    r.add_argument("--out-dir", help="directory of the result file (default: one directory "
                                     "for each run, results/<date>T<time>Z/)")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("ab", help="interleaved A/B between two endpoints")
    a.add_argument("--a", required=True, choices=sorted(ENDPOINTS))
    a.add_argument("--b", required=True, choices=sorted(ENDPOINTS))
    a.add_argument("--phases", default="transport,short,long")
    a.add_argument("--n", type=int, default=4, help="rounds for short/long")
    a.add_argument("--concurrent", type=int, default=4)
    a.add_argument("--out-dir", help="directory of the result files (default: one directory "
                                     "for each run, results/<date>T<time>Z/)")
    a.set_defaults(func=cmd_ab)

    p = sub.add_parser("report", help="aggregate a results file, or each file of a directory")
    p.add_argument("files", nargs="+", help="results files, or directories that hold them")
    p.set_defaults(func=cmd_report)

    c = sub.add_parser("compare", help="markdown table of two results files, side by side")
    c.add_argument("a", help="results file of the first endpoint, or a directory of one run")
    c.add_argument("b", nargs="?",
                   help="results file of the second endpoint (omit it if a is a directory)")
    c.add_argument("--label-a", help="name of the first endpoint in the table")
    c.add_argument("--label-b", help="name of the second endpoint in the table")
    c.add_argument("--kinds", help="csv of the phases to compare (default: all)")
    c.set_defaults(func=cmd_compare)

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
