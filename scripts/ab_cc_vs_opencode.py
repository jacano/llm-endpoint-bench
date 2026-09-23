#!/usr/bin/env python3
"""Interleaved A/B: deepseek-v4.1-flash on CommandCode vs on OpenCode (Go).

Same prompts, alternating endpoints so provider load hits both sides equally.
Writes latency_cc_ab.json / latency_oc_ab.json (one record per request).
Environment: COMMANDCODE_API_KEY and OPENCODE_GO_API_KEY from ~/.hermes/.env.
"""
import json
import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_cc_v2 as p  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ENVV = p.load_env()
UA = p.UA

CC = {"tag": "commandcode", "base": "https://api.commandcode.ai/provider/v1",
      "model": "deepseek/deepseek-v4.1-flash", "key": ENVV.get("COMMANDCODE_API_KEY"),
      "out": os.path.join(HERE, "latency_cc_ab.json"), "session": False}
OC = {"tag": "opencode-go", "base": "https://opencode.ai/zen/go/v1",
      "model": "deepseek-v4.1-flash", "key": ENVV.get("OPENCODE_GO_API_KEY"),
      "out": os.path.join(HERE, "latency_oc_ab.json"), "session": True}
EPS = [CC, OC]


def apply(ep):
    """Point the probe module globals at one endpoint."""
    p.BASE = ep["base"]
    p.MODEL = ep["model"]
    p.KEY = ep["key"]
    p.OUT = ep["out"]
    p.RECORDS = json.load(open(ep["out"])) if os.path.exists(ep["out"]) else []
    sid = str(uuid.uuid4())

    def headers():
        h = ["-H", "Authorization: Bearer %s" % ep["key"],
             "-H", "Content-Type: application/json",
             "-H", "User-Agent: " + UA,
             "-H", "Accept: application/json"]
        if ep["session"]:
            h += ["-H", "x-opencode-session: " + sid]
        return h

    p.headers = headers


def note(ep, kind, iter_no, r):
    p.rec(kind=kind, iter=iter_no, endpoint=ep["tag"], model=ep["model"], **r)


def phase_transport(ep):
    apply(ep)
    for i in range(3):
        args = ["curl", "-sS", "-o", "/dev/null", "-H", "Authorization: Bearer %s" % ep["key"],
                "-H", "User-Agent: " + UA]
        if ep["session"]:
            args += ["-H", "x-opencode-session: " + str(uuid.uuid4())]
        args += ["-w", "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} "
                       "%{time_starttransfer} %{time_total}", ep["base"] + "/models"]
        _, out, err = p.sh(args)
        parts = out.split()
        if len(parts) >= 6 and parts[0] == "200":
            r = {"code": parts[0], "dns_ms": round(float(parts[1]) * 1000, 1),
                 "tcp_ms": round(float(parts[2]) * 1000, 1), "tls_ms": round(float(parts[3]) * 1000, 1),
                 "ttfb_ms": round(float(parts[4]) * 1000, 1), "total_ms": round(float(parts[5]) * 1000, 1)}
        else:
            r = {"code": parts[0] if parts else "?", "error": (out or err).strip()[:200]}
        note(ep, "models", i + 1, r)
        print("%-14s models %s" % (ep["tag"], r), flush=True)


def rounds(phase_name, prompt, mx, n):
    for i in range(n):
        for ep in EPS:  # interleaved
            apply(ep)
            r = p.stream_parsed(prompt, mx)
            note(ep, phase_name, i + 1, r)
            print("%-14s %-12s [%d] ttft_any=%s ttft_content=%s total=%s out=%s reason=%s tok/s=%s %s"
                  % (ep["tag"], phase_name, i + 1, r["ttft_any_ms"], r["ttft_content_ms"],
                     r["total_ms"], r["out_tokens"], r["reasoning_tokens"], r["tok_per_s_total"],
                     r["error"] or ""), flush=True)


if __name__ == "__main__":
    for name, ep in (("commandcode", CC), ("opencode-go", OC)):
        print("key for %s present: %s" % (name, bool(ep["key"])))
    phase_transport(CC)
    phase_transport(OC)
    rounds("short", "Reply with exactly: pong", 64, 5)
    rounds("long", "List the integers from 1 to 250, one per line, no other text.", 1200, 4)
    rounds("prefill18k", " ".join("token%04d" % i for i in range(6000)) +
           "\n\nReply with exactly: pong", 24, 1)
