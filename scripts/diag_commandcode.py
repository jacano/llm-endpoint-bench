#!/usr/bin/env python3
"""Diagnostics: (1) does the SSE stream carry a usage block? (2) does the
`thinking` toggle actually change reasoning token counts on this gateway?"""
import json
import subprocess
import sys

import probe_commandcode as p

print("== 1. raw SSE tail (thinking disabled, long generation) ==")
body = json.dumps({"model": p.MODEL, "max_tokens": 300, "stream": True,
                   "stream_options": {"include_usage": True},
                   "thinking": {"type": "disabled"},
                   "messages": [{"role": "user", "content": "Count from 1 to 40, one per line."}]})
args = ["curl", "-sS", "-N", "-X", "POST", p.BASE + "/chat/completions"] + p.headers() + ["--data-binary", "@-"]
out = subprocess.run(args, input=body, capture_output=True, text=True, timeout=180).stdout
lines = [l for l in out.splitlines() if l.strip()]
print("total lines:", len(lines))
print("has 'usage' anywhere:", "usage" in out)
for l in lines[:3]:
    print("HEAD:", l[:220])
for l in lines[-4:]:
    print("TAIL:", l[:400])
# shape histogram of chunk payloads
shapes = {}
for l in lines:
    if not l.startswith("data:"):
        continue
    pay = l[5:].strip()
    if pay == "[DONE]":
        continue
    try:
        d = json.loads(pay)
    except Exception:
        shapes["unparseable"] = shapes.get("unparseable", 0) + 1
        continue
    if "usage" in d and d["usage"]:
        shapes["usage_line"] = shapes.get("usage_line", 0) + 1
        continue
    ch = (d.get("choices") or [{}])[0]
    delta = ch.get("delta") or {}
    if delta.get("reasoning_content"):
        shapes["reasoning_delta"] = shapes.get("reasoning_delta", 0) + 1
    elif delta.get("content"):
        shapes["content_delta"] = shapes.get("content_delta", 0) + 1
    else:
        shapes["empty_delta"] = shapes.get("empty_delta", 0) + 1
    if ch.get("finish_reason"):
        shapes["finish"] = shapes.get("finish", 0) + 1
print("chunk shapes:", shapes)

print("\n== 2. thinking toggle effect (non-streaming, 3 modes x 2) ==")
prompt = "Explain in 5 short bullet points why TCP handshakes matter."
for i in range(2):
    for mode in ("absent", "disabled", "enabled"):
        extra = {} if mode == "absent" else {"thinking": {"type": mode}}
        r = p.post(prompt, 400, extra=extra)
        p.rec(kind="diag_thinking_" + mode, iter=i + 1, **r)
        print("think=%-8s wall=%7s out=%s reasoning=%s %s"
              % (mode, r["wall_ms"], r["out_tokens"], r["reasoning_tokens"], r["error"] or ""))
