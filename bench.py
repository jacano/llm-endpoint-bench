#!/usr/bin/env python3
"""bench.py -- latency / throughput / TPS benchmark for OpenAI-compatible LLM endpoints.

An endpoint is one service under one model id, and the tool speaks the OpenAI-compatible surface
of it: `POST /chat/completions`, with the token counts and the reasoning split in the trailing
`usage` block of the response.

Phases (all timed with curl + a browser UA, so no SDK retry logic hides the tail):

  transport   DNS/TCP/TLS/TTFB on /models, fresh connection, plus three sequential
              requests in one curl invocation (reused socket) -> separates one-time
              handshake cost from per-request gateway overhead; one more request
              reads the body of /models, to confirm the model id of the route
  short       streaming, tiny answer        -> latency a user actually feels on "hi"
  long        streaming, ~600-token answer  -> TTFT split + sustained decode tok/s
  concurrent  4 parallel long answers       -> per-request and aggregate throughput

Examples
--------
    python bench.py list
    python bench.py ab --a commandcode --b opencode-go     # the whole A/B, both sides
    python bench.py ab --a commandcode --b deepseek-official --c commandcode-fast
    python bench.py run --endpoint commandcode --phases short,long
    python bench.py report results/2026-09-23T210256Z
    python bench.py compare results/2026-09-23T210256Z
    python bench.py latest --write README.md

To measure another route, add it to ENDPOINTS: the set of endpoints is data, and every command
reads it. Each run writes its files into a new directory `results/<date>T<time>Z/`, named for
the UTC time of the run, so a second run of the same day cannot mix with the first one. Give
--out-dir to put the files of several commands in one directory of a round. `report` and
`compare` accept a directory as well as a file, and results/README.md states the layout.

Keys are read from the environment of the process, then from a `.env` file beside the tool. The
name of the variable and the place it came from are printed; a value never is. Nothing in this
repo contains a credential.
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
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
#: curl is a native program: it reads the null device of the system, not the mount `/dev/null`.
NULL = "NUL" if os.name == "nt" else "/dev/null"
#: Where a key may live, after the environment of the process. A `.env` file beside the tool is
#: one path on every platform (`HERE` holds the separator of the platform), the first file that
#: defines a key wins, and names only are ever printed. The file is in `.gitignore`, so the key
#: of one route stays out of the repository.
ENV_FILES = [
    os.path.join(HERE, ".env"),
]


def default_out_dir() -> str:
    """The directory of this run: results/<date>T<time>Z/.

    The time in the name keeps the files of two runs apart, so a second run of
    the same day cannot mix with the first one. The name holds no other fact:
    the host, the operating system and the endpoint are in the `meta` block of
    each file. Give --out-dir to put the files of more than one command in one
    directory of a round.
    """
    return os.path.join(RESULTS, time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime()))

PROMPT_SHORT = "Reply with exactly: pong"
PROMPT_LONG = "List the integers from 1 to 250, one per line, no other text."
#: Parallel long answers of the phase `concurrent`. One value, so no option for it.
CONCURRENT = 4
#: The floor of the numerator of each rate, with the words for it. Below the floor the
#: rate measures the edge of a short answer rather than decoding. `tok_per_s_total`
#: spans the reasoning as well as the content, so it needs a longer answer behind it.
MIN_CONTENT_TOKENS = 10
MIN_OUTPUT_TOKENS = 50
#: The numerator of each rate: the field, the words for it, and the floor it needs.
RATE_OF = {"tok_per_s_visible": ("content_tokens", "content tokens", MIN_CONTENT_TOKENS),
           "tok_per_s_total": ("out_tokens", "output tokens", MIN_OUTPUT_TOKENS)}
#: The marker that curl appends after the body of a streaming request: its HTTP status.
#: A stream that carries no delta is a failed request, and the status is what names it.
HTTP_MARK = "BENCH_HTTP:"
#: The marker of the reused-socket probe, one transfer per URL. The numbers of that probe are
#: read from the marked tokens only: `-o` pairs with the URL that follows it, so a body that
#: leaks into the output of the three transfers can no longer be read as a timing.
REUSE_MARK = "BENCH_REUSE:"

#: Known endpoints. `deepseek-v4.1-flash` is the same model on the two routes
#: commandcode and opencode-go; only the id spelling and the transport differ.
#: `deepseek-official` is the route of the vendor itself, which the two gateways
#: above resell: same model, no gateway in the path. `commandcode` and
#: `commandcode-fast` are two model ids of one reseller, priced differently.
ENDPOINTS = {
    "commandcode": {
        "base_url": "https://api.commandcode.ai/provider/v1",
        "model": "deepseek/deepseek-v4.1-flash",
        "key_env": "COMMANDCODE_API_KEY",
        "session_header": False,
    },
    "commandcode-fast": {
        "base_url": "https://api.commandcode.ai/provider/v1",
        "model": "deepseek/deepseek-v4.1-flash-fast",
        "key_env": "COMMANDCODE_API_KEY",
        "session_header": False,
    },
    "opencode-go": {
        "base_url": "https://opencode.ai/zen/go/v1",
        "model": "deepseek-v4.1-flash",
        "key_env": "OPENCODE_GO_API_KEY",
        "key_env_alt": ["OPENCODE_API_KEY"],  # the name that another program may set for it
        "session_header": True,  # 400 MissingSessionID without it
    },
    "deepseek-official": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
        "key_env": "DEEPSEEK_API_KEY",
        "session_header": False,
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


def key_from(name: str) -> tuple[str | None, str | None]:
    """The value of a key and where it came from. The value is never printed anywhere.

    Two places, in this order, on every platform: the environment of the process, which a caller
    sets for one run (`COMMANDCODE_API_KEY=... python bench.py list`), and the `.env` file beside
    the tool, which keeps a key across runs. A key that lives anywhere else — in the environment
    of a shell that did not pass it on, or in a store of another program — is copied into that
    file by hand, which is one step and leaves the tool with no dependency of its own.
    """
    if os.environ.get(name):
        return os.environ[name], "the environment"
    found = load_env_file().get(name)
    if found:
        return found, "the .env file beside the tool"
    return None, None


def api_key(name: str) -> str | None:
    return key_from(name)[0]


def endpoint(name: str) -> dict:
    if name not in ENDPOINTS:
        sys.exit("unknown endpoint %r (known: %s)" % (name, ", ".join(ENDPOINTS)))
    ep = dict(ENDPOINTS[name])
    ep["name"] = name
    # A route may carry a second name for its key on a machine where another program set it.
    # The first name that resolves wins, and that name is the one printed.
    ep["key_names"] = [ep["key_env"]] + list(ep.get("key_env_alt") or [])
    ep["key"], ep["key_var"], ep["key_from"] = None, ep["key_env"], None
    for var in ep["key_names"]:
        value, where = key_from(var)
        if value:
            ep["key"], ep["key_var"], ep["key_from"] = value, var, where
            break
    return ep



# ---------------------------------------------------------------------- transport

def headers(ep: dict, session_id: str | None = None) -> list[str]:
    """The headers of a request: a bearer token, a content type, a browser user agent, and the
    session header that one route insists on."""
    h = ["-H", "Authorization: Bearer %s" % (ep["key"] or ""),
         "-H", "Content-Type: application/json",
         "-H", "User-Agent: " + UA,
         "-H", "Accept: application/json"]
    if ep["session_header"]:
        h += ["-H", "x-opencode-session: " + (session_id or str(uuid.uuid4()))]
    return h


def curl(args: list[str], body: str | None = None, timeout: int = 300) -> tuple[str, str]:
    """Run curl and return (stdout, stderr). The phases take their own timings.

    The pipes are decoded as UTF-8 with a replacement for a stray byte, so that a model id or an
    error message with a character outside ASCII reads the same on every platform.
    """
    r = subprocess.run(args, input=body, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return r.stdout, r.stderr


def transport(ep: dict) -> list[dict]:
    """Fresh-connection `/models` timings, a socket-reuse probe, and the model id of the route.

    `GET /models` is a body of no tokens, so its three fresh rows, its three reused rows and its
    body row are the cheapest way to separate the edge of a route from the model behind it.
    """
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
    # `-o` pairs with the URL that follows it, so the null device is named once per
    # URL: three `-o` in a row then three URLs would leave the bodies of the second
    # and the third transfer on stdout.
    args = ["curl", "-sS"]
    for _ in range(3):
        args += ["-o", NULL, url]
    args += headers(ep) + ["-w", "\n" + REUSE_MARK + "%{time_starttransfer}"]
    out, _ = curl(args, timeout=90)
    reuses = [ms(t) for t in re.findall(re.escape(REUSE_MARK) + r"([0-9.]+)", out)]
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


def ms(seconds: str) -> float:
    return round(float(seconds) * 1000, 1)


# ----------------------------------------------------------------------- streaming

def delta_of(chunk: dict) -> tuple[str, str] | None:
    """The kind and the text of one chunk of a stream, or nothing.

    `reason` is the text that the model thinks with, which a user does not read; `content` is
    the text that a user reads.
    """
    delta = ((chunk.get("choices") or [{}])[0].get("delta")) or {}
    if delta.get("reasoning") or delta.get("reasoning_content"):
        return "reason", delta.get("reasoning") or delta["reasoning_content"]
    if delta.get("content"):
        return "content", delta["content"]
    return None


def counts_of(chunk: dict, counts: dict) -> dict:
    """Merge the token counts that a chunk carries. The last value of a field wins.

    The counts of the whole answer arrive in the trailing `usage` block of the stream, with the
    reasoning split out of the output tokens, so the visible content of an answer is the
    difference of the two.
    """
    u = chunk.get("usage") or {}
    if u.get("prompt_tokens") is not None:
        counts["in_tokens"] = u["prompt_tokens"]
    if u.get("completion_tokens") is not None:
        counts["out_tokens"] = u["completion_tokens"]
    details = u.get("completion_tokens_details") or {}
    if details.get("reasoning_tokens") is not None:
        counts["reasoning_tokens"] = details["reasoning_tokens"]
    return counts


def stream(ep: dict, prompt: str, max_tokens: int) -> dict:
    """Streaming request: TTFT split + the token counts of the trailing `usage` block.

    A stream that carries no delta is a failed request and not a fast one: a gateway that
    answers `403` with a JSON error object sends no `data:` line at all, and a record of
    nulls beside the clean ones is worse than no record. The HTTP status and a sample of
    the body or of the error of curl travel with the record for that reason.
    """
    body = {"model": ep["model"], "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "stream": True,
            "stream_options": {"include_usage": True}}
    payload = json.dumps(body)
    args = ["curl", "-sS", "-N", "-X", "POST", ep["base_url"] + "/chat/completions"] + \
        headers(ep) + ["--data-binary", "@-", "-w", "\n" + HTTP_MARK + "%{http_code}"]
    t0 = time.perf_counter()
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1,
                            encoding="utf-8", errors="replace")
    proc.stdin.write(payload)
    proc.stdin.close()
    first_any = first_reason = first_content = last = None
    n_unparseable = 0
    counts = {"in_tokens": None, "out_tokens": None, "reasoning_tokens": None}
    errsample, http_code, plain = None, None, []
    for raw in proc.stdout:
        now = time.perf_counter() - t0
        raw = raw.strip()
        if not raw:
            continue
        if HTTP_MARK in raw:
            http_code = raw.split(HTTP_MARK, 1)[1].strip()
            continue
        if not raw.startswith("data:"):
            if raw.startswith("event:"):
                continue  # a protocol line that a gateway may send beside the data lines
            if len(plain) < 5:  # a body that is not the stream: an error object, a page of a proxy
                plain.append(raw[:200])
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
        counts_of(chunk, counts)
        delta = delta_of(chunk)
        if delta:
            first_any = now if first_any is None else first_any
            if delta[0] == "reason":
                first_reason = now if first_reason is None else first_reason
            else:
                first_content = now if first_content is None else first_content
            last = now
    proc.wait()
    err_text = (proc.stderr.read() or "").strip() if proc.stderr else ""
    if n_unparseable and errsample is None:
        errsample = "%d lines of the stream did not parse as JSON" % n_unparseable
    if errsample is None and first_any is None:
        # no delta at all: the request failed, and the body of the refusal or the message of
        # curl is what names it. A stream that did arrive is not judged by the text of curl.
        if plain:
            errsample = " ".join(plain)[:200]
        elif err_text:
            errsample = err_text[:200]
        else:
            errsample = ("the stream carried no delta (http %s)" % (http_code or "?")
                         if http_code else "the stream carried no delta")
    if errsample is None and counts["out_tokens"] is None:
        # the answer arrived and the route never reported what it cost: a stream that a
        # connection cut holds no counts, and a rate cannot be read out of it.
        errsample = "the stream ended without the token counts" + \
            (" (%s)" % err_text[:120] if err_text else "")
    end = time.perf_counter() - t0
    out_tok = counts["out_tokens"]
    reason_tok = counts["reasoning_tokens"]
    content_tok = out_tok - reason_tok if (out_tok is not None and reason_tok is not None) else None
    gen = (last - first_any) if (last is not None and first_any is not None) else None
    vis = (last - first_content) if (last is not None and first_content is not None) else None
    return {
        "ttft_any_ms": round(first_any * 1000, 1) if first_any is not None else None,
        "ttft_reasoning_ms": round(first_reason * 1000, 1) if first_reason is not None else None,
        "ttft_content_ms": round(first_content * 1000, 1) if first_content is not None else None,
        "total_ms": round(end * 1000, 1),
        "gen_ms": round(gen * 1000, 1) if gen else None,
        "in_tokens": counts["in_tokens"],
        "out_tokens": out_tok,
        "reasoning_tokens": reason_tok,
        "content_tokens": content_tok,
        "tok_per_s_total": round(out_tok / gen, 1) if (out_tok and gen) else None,
        "tok_per_s_visible": round(content_tok / vis, 1) if (content_tok and vis) else None,
        "http_code": http_code,
        "error": errsample,
    }


def phase_transport(ep):
    return transport(ep)


def phase_short(ep, n=5):
    return [dict(kind="short", iter=i + 1, **stream(ep, PROMPT_SHORT, 64)) for i in range(n)]


def phase_long(ep, n=4):
    return [dict(kind="long", iter=i + 1, **stream(ep, PROMPT_LONG, 1200)) for i in range(n)]


def phase_concurrent(ep):
    def one(i):
        return dict(kind="concurrent_%d" % CONCURRENT, iter=i + 1,
                    **stream(ep, PROMPT_LONG, 1200))

    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=CONCURRENT) as ex:
        rows = list(ex.map(one, range(CONCURRENT)))
    wall = time.perf_counter() - t0
    tokens = sum(r.get("out_tokens") or 0 for r in rows)
    rows.append({"kind": "concurrent_summary", "iter": CONCURRENT, "n": CONCURRENT,
                 "wall_s": round(wall, 3), "out_tokens": tokens,
                 "aggregate_tok_per_s": round(tokens / wall, 1),
                 "request_per_s": round(CONCURRENT / wall, 3)})
    return rows


PHASES = {"transport": phase_transport, "short": phase_short, "long": phase_long,
          "concurrent": phase_concurrent}


def phases_of(text: str) -> list[str]:
    """The phases that a `--phases` string names, checked against the closed set.

    A name that the tool does not hold used to reach the runner as a `KeyError`; the
    message now names the set, as the message of an unknown endpoint does.
    """
    phases = [p.strip() for p in text.split(",") if p.strip()]
    unknown = [p for p in phases if p not in PHASES]
    if unknown:
        sys.exit("unknown phase %s (known: %s)" % (", ".join(unknown), ", ".join(PHASES)))
    return phases or list(PHASES)


# ------------------------------------------------------------------------- running

def run_phases(ep: dict, phases: list[str]) -> list[dict]:
    recs = []
    for name in phases:
        rows = PHASES[name](ep)
        for r in rows:
            r.update({"endpoint": ep["name"], "model": ep["model"]})
            print("  %-16s %-12s %s" % (ep["name"], name, summarize(r)), flush=True)
        recs += rows
    return recs


def summarize(r: dict) -> str:
    if r.get("error"):
        return "ERROR%s %s" % (" http=%s" % r["http_code"] if r.get("http_code") else "",
                               str(r["error"])[:120])
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
                        "runner": "bench.py"},
               "records": recs}
    # A fixed encoding and a fixed line ending, so that a record of one platform is the record of
    # another byte for byte: a text stream would translate `\n` on Windows.
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=1)
    return path


# ------------------------------------------------------------------------- reports

def load_records(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        return data.get("records", [])
    return data  # bare list, e.g. the raw session dumps in results/


def load_meta(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
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
        sys.exit("compare: %s holds %d tag(s) (%s). Name the two files of the pair: a round of "
                 "three holds three pairs, and each of them is one command."
                 % (directory, len(tags), ", ".join(sorted(tags)) or "none"))
    pair = [max(rows)[1] for _, rows in sorted(tags.items())]
    return pair[0], pair[1]


def med(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return round(st.median(vals), 1) if vals else None


def present(rows: list[dict], key: str) -> int:
    """How many records of a phase hold a value for this metric.

    A record may hold a metric as null, and a median of 19 values is not a median of 20: an
    answer that never writes a visible token has no delay to its first visible token.
    """
    return len([r for r in rows if isinstance(r.get(key), (int, float))])


def thin_answer(key: str, *rowsets: list[dict]) -> tuple[int, str] | None:
    """The floor and the words of the numerator when a rate rests on too few tokens.

    Every rowset given must hold enough tokens: a rate that one side of a comparison
    cannot support is not a rate for either side.
    """
    if key not in RATE_OF:
        return None
    field, words, floor = RATE_OF[key]
    counts = [med([r.get(field) for r in rows]) for rows in rowsets if rows]
    counts = [c for c in counts if c is not None]
    return (floor, words) if (counts and min(counts) < floor) else None


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
            row = rows[0]
            print("  models_body: %s" % {m: row[m] for m in ("n_ids", "target_present")
                                         if row.get(m) is not None})
            continue
        else:
            keys = ["ttft_any_ms", "ttft_content_ms", "total_ms", "in_tokens", "out_tokens",
                    "reasoning_tokens", "content_tokens", "tok_per_s_total", "tok_per_s_visible"]
        print("  %-18s n=%d" % (k, len(rows)))
        absent = []
        for key in keys:
            vals = [r.get(key) for r in rows]
            m = med(vals)
            if m is None:
                # A phase may hold no value for a row: an answer that wrote no visible token has
                # no delay to its first one, and a route that never reported a count has none.
                # Name the row rather than let a reader look for one the table cannot hold.
                absent.append(key)
                continue
            thin = thin_answer(key, rows)
            if thin:
                # a rate over a handful of tokens is a large number without meaning
                print("      %-18s skipped: the answer holds fewer than %d %s"
                      % (key, thin[0], thin[1]))
                continue
            nums = [v for v in vals if isinstance(v, (int, float))]
            print("      %-18s median %-9s min %-9s max %-9s" % (key, m, round(min(nums), 1), round(max(nums), 1)))
        if absent:
            print("      %-18s %s (no clean record of this phase holds one)" % ("not reported", ", ".join(absent)))


# ----------------------------------------------------------------- comparison

#: Metrics where a low value is better. Every other metric is a rate.
LOWER_IS_BETTER = {"dns_ms", "tcp_ms", "tls_ms", "ttfb_ms", "total_ms", "wall_s",
                   "ttft_any_ms", "ttft_content_ms"}
#: A difference below this fraction is noise (see the limits in ANALYSIS.md).
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
#: tokens is not a better result, a shorter wall clock with fewer tokens is not either, and
#: a route that lists more model ids is not faster.
NO_VERDICT = {"in_tokens", "out_tokens", "reasoning_tokens", "content_tokens", "wall_s", "n_ids"}
#: A verdict needs this many samples behind each side. One request proves nothing, as the
#: limits in ANALYSIS.md say.
MIN_SAMPLES = 3
#: Above this fraction of difference in the output tokens of the two sides, a timing or a
#: rate of the phase measures the work of the answer as well as the route, and the tool says so.
WORK_DIFF = 0.20


def metrics_for(kind: str) -> list[str]:
    return COMPARE_METRICS.get(kind, COMPARE_DEFAULT)


def compare(path_a: str, path_b: str) -> None:
    """Print a markdown table of the median of each metric of two result files."""
    ra = [r for r in load_records(path_a) if not r.get("error")]
    rb = [r for r in load_records(path_b) if not r.get("error")]
    la = str(ra[0].get("endpoint") if ra else "A")
    lb = str(rb[0].get("endpoint") if rb else "B")
    ks = sorted({str(r.get("kind")) for r in ra + rb if r.get("kind")})
    print("%s (%d records)" % (path_a, len(ra)))
    print("  " + generation_line(path_a))
    print("%s (%d records)" % (path_b, len(rb)))
    print("  " + generation_line(path_b))
    print("")
    print("| Kind | Metric | %s | %s | %s / %s | n | Better |" % (la, lb, lb, la))
    print("|---|---|---|---|---|---|---|")
    hidden = {}
    few_samples = set()
    work = {}
    one_sided = {}
    for kind in ks:
        rows_a = [r for r in ra if r.get("kind") == kind]
        rows_b = [r for r in rb if r.get("kind") == kind]
        if not rows_a and not rows_b:
            continue
        n = min(len(rows_a), len(rows_b))
        if n < MIN_SAMPLES:
            few_samples.add(kind)
        out_a = med([r.get("out_tokens") for r in rows_a])
        out_b = med([r.get("out_tokens") for r in rows_b])
        if out_a and out_b and max(out_a, out_b) / min(out_a, out_b) - 1 > WORK_DIFF:
            work[kind] = (out_a, out_b)
        for key in metrics_for(kind):
            a = med([r.get(key) for r in rows_a])
            b = med([r.get(key) for r in rows_b])
            if a is None and b is None:
                continue
            if (a is None) != (b is None):
                # A row can hold a value on one side only: an answer that wrote no visible token
                # has no delay to its first one. Name the rows instead of leaving a bare dash.
                one_sided.setdefault(key, set()).add(kind)
            thin = thin_answer(key, rows_a, rows_b)
            if thin:
                hidden.setdefault(key, [set(), thin])[0].add(kind)
                continue
            ratio = round(b / a, 2) if (a and b) else None
            print("| %s | %s | %s | %s | %s | %d/%d | %s |"
                  % (kind, key, fmt(a), fmt(b), fmt(ratio), present(rows_a, key), present(rows_b, key),
                     verdict(key, a, b, la, lb, n)))
    for key in sorted(one_sided):
        print("")
        print("`%s` is empty on one side of %s: no clean record of that side holds a value for it."
              % (key, ", ".join(sorted(one_sided[key]))))
    for key in sorted(hidden):
        kinds_hidden, (floor, words) = hidden[key]
        print("")
        print("`%s` is not shown for %s: the median answer of the phase holds fewer than "
              "%d %s." % (key, ", ".join(sorted(kinds_hidden)), floor, words))
    if few_samples:
        print("")
        print("The column `Better` stays empty for the phases %s: the tool asks for %d samples "
              "on each side before it names a winner, and one sample proves nothing."
              % (", ".join(sorted(few_samples)), MIN_SAMPLES))
    if work:
        print("")
        print("The two sides do not write the same number of output tokens in %s, so a timing "
              "or a rate of those phases measures the work of the answer as well as the route."
              % ", ".join("`%s` (%s against %s)" % (k, fmt(work[k][0]), fmt(work[k][1]))
                          for k in sorted(work)))
    print("")
    print("The column `%s / %s` is the value of %s divided by the value of %s. "
          "A difference below %d percent shows `same`. A ratio below 1 belongs to a rate, "
          "where a large number is better. The column `Better` stays empty for a count, "
          "because a count is not a score." % (lb, la, lb, la, NOISE * 100))


def verdict(key: str, a, b, label_a: str = "A", label_b: str = "B", n: int | None = None) -> str:
    if key in NO_VERDICT or a is None or b is None or not a or not b:
        return "-"
    if n is not None and n < MIN_SAMPLES:
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
    """Run an interleaved round of two endpoints, or of three when --c names one.

    A round of three is the way to compare a pair of routes against one anchor without an indirect
    quotient: every round of the `short` and `long` phases touches all three in turn, so the load
    of the provider hits them the same way. `compare` takes any two of the files that the command
    writes.
    """
    eps = [endpoint(args.a), endpoint(args.b)] + ([endpoint(args.c)] if args.c else [])
    if len({ep["name"] for ep in eps}) != len(eps):
        sys.exit("ab: name each endpoint once (%s)" % ", ".join(ep["name"] for ep in eps))
    for ep in eps:
        if not ep["key"]:
            sys.exit("no key for %s (%s)" % (ep["name"], " or ".join(ep["key_names"])))
    phases = phases_of(args.phases)
    out = {ep["name"]: [] for ep in eps}
    for phase in phases:
        n = args.n if phase in ("short", "long") else 1
        for i in range(n):
            for ep in eps:  # interleaved: the load of the provider hits every side equally
                rows = PHASES[phase](ep)
                for r in rows:
                    r.update({"endpoint": ep["name"], "model": ep["model"]})
                    print("  %-22s %-10s [%d] %s" % (ep["name"], phase, i + 1, summarize(r)),
                          flush=True)
                out[ep["name"]] += rows
    for ep in eps:
        path = write_results(out[ep["name"]], ep, phases, args.out_dir or default_out_dir(),
                             prefix="ab_")
        print("wrote", path)


def cmd_run(args) -> None:
    ep = endpoint(args.endpoint)
    if not ep["key"]:
        sys.exit("no API key for %s: set %s in the environment, or in the .env file beside the "
                 "tool" % (ep["name"], " or ".join(ep["key_names"])))
    phases = phases_of(args.phases)
    print("endpoint=%s model=%s phases=%s" % (ep["name"], ep["model"], phases))
    recs = run_phases(ep, phases)
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
    compare(a, b)


# -------------------------------------------------------------------- the latest

#: The two markers that hold the table of `latest` inside a document. The command replaces what
#: stands between them and touches nothing else, so the table of a README is one command away
#: from the records and a reader of it never reads a hand-kept number.
LATEST_BEGIN = "<!-- latest:begin -->"
LATEST_END = "<!-- latest:end -->"


def latest_rows(directory: str) -> list[dict]:
    """The newest result file of each endpoint under a results tree, with the medians of its phases.

    One row for each endpoint that any file measures, taken from the newest file that measures it:
    a round of one endpoint does not hide the rows of the rounds before it, and every row carries
    the time of its own round, because two rows of one table may come from two different rounds and
    the absolute values of two rounds are not directly comparable.
    """
    rows = {}
    for name in sorted(os.listdir(directory)):
        sub = os.path.join(directory, name)
        if not os.path.isdir(sub):
            continue
        for fname in sorted(os.listdir(sub)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(sub, fname)
            try:
                meta = load_meta(path)
                recs = [r for r in load_records(path) if not r.get("error")]
            except Exception:
                continue
            if not recs:
                continue
            ep = meta.get("endpoint") or recs[0].get("endpoint")
            if not ep:
                continue
            by_kind = {}
            for r in recs:
                by_kind.setdefault(str(r.get("kind")), []).append(r)
            stamp = str(meta.get("started_utc") or name)

            def m(kind, key):
                return med([r.get(key) for r in by_kind.get(kind, [])])

            row = {
                "endpoint": ep, "model": meta.get("model", "?"),
                "stamp": stamp, "round": name, "file": fname,
                "short_ttft": m("short", "ttft_content_ms"),
                "long_ttft": m("long", "ttft_content_ms"),
                "long_total": m("long", "total_ms"),
                "decode": m("long", "tok_per_s_total"),
                "visible": m("long", "tok_per_s_visible"),
                "par_one": m("concurrent_4", "tok_per_s_total"),
                "par_all": m("concurrent_summary", "aggregate_tok_per_s"),
                "edge": m("models_reuse", "ttfb_ms"),
                "out_tokens": m("long", "out_tokens"),
                "reasoning": m("long", "reasoning_tokens"),
                "content": m("long", "content_tokens"),
                "n_short": present(by_kind.get("short", []), "ttft_content_ms"),
                "n_long": present(by_kind.get("long", []), "ttft_content_ms"),
            }
            if ep not in rows or stamp > rows[ep]["stamp"]:
                rows[ep] = row
    return list(rows.values())


def latest_table(rows: list[dict], by: str = "short") -> str:
    """The markdown of the one table: a line for each endpoint, fastest first.

    The order is the delay of a short answer, the row that a user feels; `by` asks for another
    one. An endpoint that never measured that row goes last, with a dash in every cell it cannot
    fill, which is the same rule that `report` and `compare` follow.
    """
    order = {"short": ("short_ttft", False), "long": ("long_ttft", False),
             "decode": ("decode", True), "visible": ("visible", True),
             "total": ("long_total", False)}
    key, reverse = order.get(by, order["short"])
    rows = sorted(rows, key=lambda r: (r.get(key) is None,
                                       (r.get(key) if r.get(key) is not None else 0.0) *
                                       (-1 if reverse else 1)))
    out = ["| Endpoint | Round (UTC) | Short: TTFT visible | Long: TTFT visible | Long: total "
           "| Long: decode | Long: visible | 4 parallel: one | 4 parallel: total | Long: output "
           "tokens | TTFB, ready socket |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cells = [cell(r["short_ttft"], "ms"), cell(r["long_ttft"], "ms"),
                 cell(r["long_total"], "ms"), cell(r["decode"], "tokens/s"),
                 cell(r["visible"], "tokens/s"), cell(r["par_one"], "tokens/s"),
                 cell(r["par_all"], "tokens/s"), cell(r["out_tokens"]), cell(r["edge"], "ms")]
        out.append("| `%s` | %s | %s |" % (r["endpoint"], pretty_stamp(r["stamp"]),
                                           " | ".join(cells)))
    newest = max((r["stamp"] for r in rows), default="?")
    out.append("")
    out.append("%d endpoints across %d rounds under `results/`, fastest short answer first. Each "
               "row comes from the newest file that measures that endpoint, and the newest round of "
               "the tree is %s; a row names its own round, so two rows of this table can come from "
               "two rounds and the absolute values of two rounds are not directly comparable "
               "(`ANALYSIS.md` states that limit). `Long: output tokens` is the median work of that "
               "phase: read a rate beside it, and prefer the rate of the visible content when the "
               "work of two rows differs by more than a fifth. `TTFB, ready socket` is the "
               "per-request cost of the edge, the row that separates the two halves of a route."
               % (len(rows), len({r["round"] for r in rows}), pretty_stamp(newest)))
    return "\n".join(out)


def cell(v, unit: str = "") -> str:
    """A value of the table, or a dash where the phase holds none."""
    if v is None:
        return "-"
    return ("%g %s" % (v, unit)).strip()


def pretty_stamp(stamp: str) -> str:
    """`20260929T115801Z` reads as `2026-09-29 11:58Z` in a table."""
    if len(stamp) >= 15 and stamp[8] == "T":
        return "%s-%s-%s %s:%sZ" % (stamp[0:4], stamp[4:6], stamp[6:8], stamp[9:11], stamp[11:13])
    return stamp


def write_block(path: str, block: str) -> None:
    """Replace the text between the two markers of a document with `block`, and nothing else."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if LATEST_BEGIN not in text or LATEST_END not in text:
        sys.exit("latest: %s holds no %s ... %s pair to fill" % (path, LATEST_BEGIN, LATEST_END))
    head, _, rest = text.partition(LATEST_BEGIN)
    _, _, tail = rest.partition(LATEST_END)
    new = head + LATEST_BEGIN + "\n" + block.rstrip() + "\n" + LATEST_END + tail
    if new == text:
        print("unchanged", path)
        return
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    print("updated", path)


def cmd_latest(args) -> None:
    """Print the one table of the newest results, and fill it into a document on request."""
    rows = latest_rows(args.dir)
    if not rows:
        sys.exit("latest: no result file under %s" % args.dir)
    block = latest_table(rows, args.by)
    if args.write:
        write_block(args.write, block)
    else:
        print(block)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show known endpoints")

    r = sub.add_parser("run", help="benchmark one endpoint")
    r.add_argument("--endpoint", required=True, choices=sorted(ENDPOINTS))
    r.add_argument("--phases", default=",".join(PHASES), help="csv of: %s" % ",".join(PHASES))
    r.add_argument("--out-dir", help="directory of the result file (default: one directory "
                                     "for each run, results/<date>T<time>Z/)")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("ab", help="interleaved A/B between two endpoints, or three with --c")
    a.add_argument("--a", required=True, choices=sorted(ENDPOINTS))
    a.add_argument("--b", required=True, choices=sorted(ENDPOINTS))
    a.add_argument("--c", choices=sorted(ENDPOINTS),
                   help="a third endpoint, for a round of three; the three are interleaved, and "
                        "a comparison of any two of them is a comparison of two sides of one round")
    a.add_argument("--phases", default=",".join(PHASES), help="csv of: %s" % ",".join(PHASES))
    a.add_argument("--n", type=int, default=4, help="rounds for short/long")
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
    c.set_defaults(func=cmd_compare)

    l = sub.add_parser("latest", help="one table of the newest results of every endpoint")
    l.add_argument("--dir", default=RESULTS, help="the results tree to read (default: results/)")
    l.add_argument("--by", default="short",
                   choices=["short", "long", "total", "decode", "visible"],
                   help="the row that orders the table, fastest first (default: short)")
    l.add_argument("--write", metavar="FILE",
                   help="fill the table into FILE between the markers %s and %s"
                        % (LATEST_BEGIN, LATEST_END))
    l.set_defaults(func=cmd_latest)

    args = ap.parse_args()
    if args.cmd == "list":
        for name, cfg in ENDPOINTS.items():
            ep = endpoint(name)
            state = ("found (%s, from %s)" % (ep["key_var"], ep["key_from"])) if ep["key"] \
                else "MISSING"
            print("%-18s %-44s model=%-30s key=%s %s%s" % (
                name, cfg["base_url"], cfg["model"], ep["key_var"], state,
                "  (+ x-opencode-session)" if cfg["session_header"] else ""))
        return
    args.func(args)


if __name__ == "__main__":
    main()
