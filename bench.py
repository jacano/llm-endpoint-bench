#!/usr/bin/env python3
"""bench.py -- latency / throughput / TPS benchmark for OpenAI-compatible and Messages endpoints.

An endpoint names one surface of one route, and every command of the tool works on both:

  openai-completions   POST /chat/completions, the shape of the OpenAI API. The token counts
                       and the reasoning split arrive in a trailing `usage` block.
  anthropic-messages   POST /v1/messages, the shape of the Anthropic Messages API, with the
                       key in `x-api-key` and a version header. The counts arrive split in
                       two: the input at `message_start`, the output at `message_delta`. That
                       surface reports no reasoning split, so `content_tokens` and the rate of
                       the visible content are not rows of a round of it.

Phases (all timed with curl + a browser UA, so no SDK retry logic hides the tail):

  transport   DNS/TCP/TLS/TTFB on /models, fresh connection, plus three sequential
              requests in one curl invocation (reused socket) -> separates one-time
              handshake cost from per-request gateway overhead; one more request
              reads the body of /models, to confirm the model id of the route.
              A Messages route has no /models, so the probe of that phase is the
              smallest message the surface takes: one token, streamed.
  short       streaming, tiny answer        -> latency a user actually feels on "hi"
  long        streaming, ~600-token answer  -> TTFT split + sustained decode tok/s
  concurrent  4 parallel long answers       -> per-request and aggregate throughput

Token counts come from the response of the surface: the `usage` block of the OpenAI-compatible
one, the two usage events of the Messages one.

Examples
--------
    python bench.py list
    python bench.py ab --a commandcode --b opencode-go     # the whole A/B, both sides
    python bench.py ab --a commandcode --b deepseek-official --c commandcode-fast
    python bench.py ab --a deepseek-official --b deepseek-official-messages
    python bench.py run --endpoint commandcode --phases short,long
    python bench.py report results/2026-09-23T210256Z
    python bench.py compare results/2026-09-23T210256Z

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
#: The two surfaces that a route may speak, with the path of a streaming request and the path
#: of the transport probe of each one. A route of the Messages surface lists no model ids, so
#: its probe is the smallest message that the surface takes.
OPENAI = "openai-completions"
MESSAGES = "anthropic-messages"
#: The version of the Messages surface that the tool asks for. A route of that surface refuses
#: a request that carries no version, and this value is the one that every implementation takes.
MESSAGES_VERSION = "2023-06-01"

#: Known endpoints. `deepseek-v4.1-flash` is the same model on the two routes
#: commandcode and opencode-go; only the id spelling and the transport differ.
#: `deepseek-official` and `deepseek-official-messages` are the two surfaces of the
#: route of the vendor itself, which the two gateways above resell: same model, no
#: gateway in the path. An endpoint takes one surface, so a route of two surfaces
#: takes two entries and the tool can put them against each other.
ENDPOINTS = {
    "commandcode": {
        "base_url": "https://api.commandcode.ai/provider/v1",
        "model": "deepseek/deepseek-v4.1-flash",
        "key_env": "COMMANDCODE_API_KEY",
        "api": OPENAI,
        "session_header": False,
    },
    "commandcode-fast": {
        "base_url": "https://api.commandcode.ai/provider/v1",
        "model": "deepseek/deepseek-v4.1-flash-fast",
        "key_env": "COMMANDCODE_API_KEY",
        "api": OPENAI,
        "session_header": False,
    },
    "opencode-go": {
        "base_url": "https://opencode.ai/zen/go/v1",
        "model": "deepseek-v4.1-flash",
        "key_env": "OPENCODE_GO_API_KEY",
        "key_env_alt": ["OPENCODE_API_KEY"],  # the name that another program may set for it
        "api": OPENAI,
        "session_header": True,  # 400 MissingSessionID without it
    },
    "deepseek-official": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
        "key_env": "DEEPSEEK_API_KEY",
        "api": OPENAI,
        "session_header": False,
    },
    "deepseek-official-messages": {
        "base_url": "https://api.deepseek.com/anthropic",
        "model": "deepseek-flash",
        "key_env": "DEEPSEEK_API_KEY",
        "api": MESSAGES,
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
    ep["api"] = ep.get("api", OPENAI)
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
    """The headers of a request on the surface of the endpoint.

    The two surfaces authenticate differently: the OpenAI-compatible one takes a bearer token
    and the Messages one takes the key in `x-api-key` with the version of the protocol beside
    it. Everything else — the content type, a browser user agent that a gateway may insist on,
    and the session header of one route — is the same for both.
    """
    h = ["-H", "Content-Type: application/json",
         "-H", "User-Agent: " + UA,
         "-H", "Accept: application/json"]
    if ep["api"] == MESSAGES:
        h += ["-H", "x-api-key: " + (ep["key"] or ""),
              "-H", "anthropic-version: " + MESSAGES_VERSION]
    else:
        h = ["-H", "Authorization: Bearer %s" % (ep["key"] or "")] + h
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
    """The transport of a route: the handshake, a ready socket, and the model of the route.

    A route of the OpenAI-compatible surface answers `GET /models`, which is a body of no
    tokens: the three fresh rows, the three reused rows and the body row are cheap. A route
    of the Messages surface lists no model ids at all, so its probe is the smallest message
    that the surface takes — one token, streamed — and its rows carry the name of that probe
    in the field `probe`. The TTFB of that probe holds the first event of the model as well
    as the edge of the route, which the summary of such a round states.
    """
    if ep["api"] == MESSAGES:
        return transport_messages(ep)
    recs = []
    url = ep["base_url"] + "/models"
    for i in range(3):
        args = ["curl", "-sS", "-o", NULL] + headers(ep) + \
            ["-w", "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} "
                   "%{time_starttransfer} %{time_total}", url]
        out, err = curl(args, timeout=60)
        p = out.split()
        if len(p) >= 6 and p[0] == "200":
            recs.append({"kind": "models", "iter": i + 1, "code": p[0], "probe": "GET /models",
                         "dns_ms": ms(p[1]), "tcp_ms": ms(p[2]), "tls_ms": ms(p[3]),
                         "ttfb_ms": ms(p[4]), "total_ms": ms(p[5])})
        else:
            recs.append({"kind": "models", "iter": i + 1, "code": p[0] if p else "?",
                         "probe": "GET /models", "error": (out or err).strip()[:200]})
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
        recs.append({"kind": "models_reuse", "iter": i + 1, "ttfb_ms": t, "probe": "GET /models"})
    # the body of /models names the model ids of the route: one request, and a
    # results file says whether the model of this endpoint exists on this route.
    out, err = curl(["curl", "-sS", url] + headers(ep), timeout=60)
    try:
        ids = [m.get("id") for m in json.loads(out).get("data", [])]
    except Exception:
        ids = None
    recs.append({"kind": "models_body", "iter": 1, "probe": "GET /models",
                 "n_ids": len(ids) if ids else None,
                 "target_present": ep["model"] in ids if ids else None,
                 "error": None if ids else (out or err).strip()[:200]})
    return recs


def transport_messages(ep: dict) -> list[dict]:
    """The same three transport rows on a surface whose probe is a message of one token."""
    recs = []
    url = ep["base_url"] + "/v1/messages"
    probe = json.dumps({"model": ep["model"], "max_tokens": 1, "stream": True,
                        "messages": [{"role": "user", "content": PROMPT_SHORT}]})
    fmt = ("%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} "
           "%{time_starttransfer} %{time_total}")
    for i in range(3):
        args = ["curl", "-sS", "-o", NULL, "-X", "POST", url] + headers(ep) + \
            ["--data-binary", probe, "-w", fmt]
        out, err = curl(args, timeout=60)
        p = out.split()
        if len(p) >= 6 and p[0] == "200":
            recs.append({"kind": "models", "iter": i + 1, "code": p[0],
                         "probe": "POST /v1/messages, one token",
                         "dns_ms": ms(p[1]), "tcp_ms": ms(p[2]), "tls_ms": ms(p[3]),
                         "ttfb_ms": ms(p[4]), "total_ms": ms(p[5])})
        else:
            recs.append({"kind": "models", "iter": i + 1, "code": p[0] if p else "?",
                         "probe": "POST /v1/messages, one token",
                         "error": (out or err).strip()[:200]})
    args = ["curl", "-sS"]
    for _ in range(3):
        args += ["-o", NULL, url]
    args += ["-X", "POST"] + headers(ep) + \
        ["--data-binary", probe, "-w", "\n" + REUSE_MARK + "%{time_starttransfer}"]
    out, _ = curl(args, timeout=90)
    reuses = [ms(t) for t in re.findall(re.escape(REUSE_MARK) + r"([0-9.]+)", out)]
    for i, t in enumerate(reuses):
        recs.append({"kind": "models_reuse", "iter": i + 1, "ttfb_ms": t,
                     "probe": "POST /v1/messages, one token"})
    # the stream of that probe names the model that the route served, which is what the body
    # of `/models` names on the other surface.
    out, err = curl(["curl", "-sS", "-X", "POST", url] + headers(ep) +
                    ["--data-binary", probe], timeout=60)
    served = None
    try:
        for line in out.splitlines():
            if line.startswith("data:"):
                served = (json.loads(line[5:].strip()).get("message") or {}).get("model")
                if served:
                    break
    except Exception:
        served = None
    recs.append({"kind": "models_body", "iter": 1, "probe": "POST /v1/messages, one token",
                 "model_served": served,
                 "target_present": served == ep["model"] if served else None,
                 "error": None if served else (out or err).strip()[:200]})
    return recs


def ms(seconds: str) -> float:
    return round(float(seconds) * 1000, 1)


# ----------------------------------------------------------------------- streaming

def request_of(ep: dict, prompt: str, max_tokens: int) -> tuple[list[str], str]:
    """The arguments of curl and the body of one streaming request on the surface of the endpoint.

    The two surfaces take the same three fields and differ in the rest: the Messages surface
    wants `max_tokens` always and knows no `stream_options`, and its path is `/v1/messages`
    where the other one is `/chat/completions`.
    """
    if ep["api"] == MESSAGES:
        body = {"model": ep["model"], "max_tokens": max_tokens, "stream": True,
                "messages": [{"role": "user", "content": prompt}]}
        url = ep["base_url"] + "/v1/messages"
    else:
        body = {"model": ep["model"], "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "stream": True,
                "stream_options": {"include_usage": True}}
        url = ep["base_url"] + "/chat/completions"
    args = ["curl", "-sS", "-N", "-X", "POST", url] + headers(ep) + \
        ["--data-binary", "@-", "-w", "\n" + HTTP_MARK + "%{http_code}"]
    return args, json.dumps(body)


def delta_of(ep: dict, chunk: dict) -> tuple[str, str] | None:
    """The kind and the text of one chunk of a stream, or nothing.

    The two surfaces name the same thing differently. `reason` is the text that the model
    thinks with, which a user does not read; `content` is the text that a user reads.
    """
    if ep["api"] == MESSAGES:
        if chunk.get("type") == "content_block_delta":
            d = chunk.get("delta") or {}
            if d.get("type") == "thinking_delta" and d.get("thinking"):
                return "reason", d["thinking"]
            if d.get("type") == "text_delta" and d.get("text"):
                return "content", d["text"]
        return None
    delta = ((chunk.get("choices") or [{}])[0].get("delta")) or {}
    if delta.get("reasoning") or delta.get("reasoning_content"):
        return "reason", delta.get("reasoning") or delta["reasoning_content"]
    if delta.get("content"):
        return "content", delta["content"]
    return None


def counts_of(ep: dict, chunk: dict, counts: dict) -> dict:
    """Merge the token counts of one chunk. The last value of a field wins.

    The OpenAI-compatible surface reports the counts of the whole answer in a trailing `usage`
    block, and it splits the reasoning out of the output tokens. The Messages surface reports
    the input at the start of the stream and the output at its end, with no reasoning split:
    `reasoning_tokens` and `content_tokens` stay empty on that surface, and the rate of the
    visible content is not a row of a round of it. That is a property of the surface and not
    of the model, and the summary of such a round states it.
    """
    u = chunk.get("usage") or {}
    if ep["api"] == MESSAGES:
        if u.get("input_tokens") is not None:
            counts["in_tokens"] = u["input_tokens"]
        if u.get("output_tokens") is not None:
            counts["out_tokens"] = u["output_tokens"]
    else:
        if u.get("prompt_tokens") is not None:
            counts["in_tokens"] = u["prompt_tokens"]
        if u.get("completion_tokens") is not None:
            counts["out_tokens"] = u["completion_tokens"]
    details = u.get("output_tokens_details") or u.get("completion_tokens_details") or {}
    if details.get("reasoning_tokens") is not None:
        counts["reasoning_tokens"] = details["reasoning_tokens"]
    return counts


def error_of(ep: dict, chunk: dict) -> str | None:
    """The text of an error that a chunk carries, in the shape of the surface."""
    if chunk.get("type") == "error":
        return json.dumps(chunk.get("error") or chunk)[:200]
    return None


def stream(ep: dict, prompt: str, max_tokens: int) -> dict:
    """Streaming request on the surface of the endpoint: TTFT split + the token counts.

    A stream that carries no delta is a failed request and not a fast one: a gateway that
    answers `403` with a JSON error object sends no `data:` line at all, and a record of
    nulls beside the clean ones is worse than no record. The HTTP status and a sample of
    the body or of the error of curl travel with the record for that reason.
    """
    args, payload = request_of(ep, prompt, max_tokens)
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
                continue  # a protocol line of the Messages surface, not a body of a refusal
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
        errsample = errsample or error_of(ep, chunk)
        counts_of(ep, chunk, counts)
        delta = delta_of(ep, chunk)
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
        # the answer arrived and the surface never reported what it cost: a stream that a
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
                        "api": ep["api"], "phases": phases, "started_utc": stamp,
                        "host": platform.node(), "runner": "bench.py"},
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
    """When and where a file was written. A file of a session before bench.py holds no meta.

    The field `api` names the surface of the round, and a file written before the tool spoke
    two surfaces holds none: every one of those measured the OpenAI-compatible surface, which
    is what the reader of such a file is told here.
    """
    m = load_meta(path)
    if not m:
        return "no meta block: the file records no time of the run"
    return "generated %s on %s | endpoint %s | api %s | model %s | phases %s" % (
        m.get("started_utc", "?"), m.get("host", "?"), m.get("endpoint", "?"),
        m.get("api", OPENAI), m.get("model", "?"), ",".join(m.get("phases") or []))


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
            # the two surfaces report different facts here: the ids of the route and the id
            # that the route served. Print the ones that this surface holds.
            print("  models_body: %s" % {m: row[m] for m in ("n_ids", "model_served",
                                                             "target_present")
                                         if row.get(m) is not None})
            continue
        else:
            keys = ["ttft_any_ms", "ttft_content_ms", "total_ms", "in_tokens", "out_tokens",
                    "reasoning_tokens", "content_tokens", "tok_per_s_total", "tok_per_s_visible"]
        head = "  %-18s n=%d" % (k, len(rows))
        if rows[0].get("probe"):
            head += "  probe: %s" % rows[0]["probe"]
        print(head)
        absent = []
        for key in keys:
            vals = [r.get(key) for r in rows]
            m = med(vals)
            if m is None:
                # A surface reports what it reports: the Messages one carries no reasoning
                # split, so three rows of a phase of it have no value at all. Say so, rather
                # than let a reader look for a row that the table cannot hold.
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
                # One surface may report what the other does not: the Messages one carries no
                # reasoning split, so `content_tokens` and the rate of the visible content have
                # no value on that side of a table. Name the rows instead of leaving a dash.
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
        print("`%s` is empty on one side of %s: the surface of that side does not report the "
              "value, or no clean record of the phase holds it."
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
    print("endpoint=%s api=%s model=%s phases=%s" % (ep["name"], ep["api"], ep["model"], phases))
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

    args = ap.parse_args()
    if args.cmd == "list":
        for name, cfg in ENDPOINTS.items():
            ep = endpoint(name)
            state = ("found (%s, from %s)" % (ep["key_var"], ep["key_from"])) if ep["key"] \
                else "MISSING"
            print("%-28s %-42s api=%-20s model=%-28s key=%s %s%s" % (
                name, cfg["base_url"], ep["api"], cfg["model"], ep["key_var"], state,
                "  (+ x-opencode-session)" if cfg["session_header"] else ""))
        return
    args.func(args)


if __name__ == "__main__":
    main()
