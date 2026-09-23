#!/usr/bin/env python3
"""Side-by-side medians for the CommandCode vs OpenCode A/B run."""
import json
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [("commandcode", "latency_cc_ab.json"), ("opencode-go", "latency_oc_ab.json")]


def med(vals):
    v = [x for x in vals if isinstance(x, (int, float))]
    return round(st.median(v), 1) if v else None


def load(name, fn):
    path = os.path.join(HERE, fn)
    if not os.path.exists(path):
        return []
    return [r for r in json.load(open(path)) if not r.get("error")]


DATA = {name: load(name, fn) for name, fn in FILES}
for name, rows in DATA.items():
    print("%s: %d clean records" % (name, len(rows)))

METRICS = [("models", "tls_ms"), ("models", "ttfb_ms"),
           ("short", "ttft_any_ms"), ("short", "ttft_content_ms"), ("short", "total_ms"),
           ("long", "ttft_any_ms"), ("long", "ttft_content_ms"), ("long", "total_ms"),
           ("long", "out_tokens"), ("long", "reasoning_tokens"),
           ("long", "tok_per_s_total"), ("long", "tok_per_s_visible"),
           ("prefill18k", "in_tokens"), ("prefill18k", "ttft_any_ms"), ("prefill18k", "total_ms")]

print("\n%-16s %-18s %12s %12s %8s" % ("phase", "metric", "commandcode", "opencode-go", "ratio"))
for kind, key in METRICS:
    vals = {}
    for name, rows in DATA.items():
        sel = [r for r in rows if r.get("kind") == kind]
        vals[name] = med([r.get(key) for r in sel])
    a, b = vals["commandcode"], vals["opencode-go"]
    ratio = round(b / a, 2) if (a and b) else None
    print("%-16s %-18s %12s %12s %8s" % (kind, key, a, b, ratio))

print("\nconcurrency summaries:")
for name, rows in DATA.items():
    for r in rows:
        if r.get("kind") == "concurrent_summary":
            print("   %-14s %s" % (name, {k: r[k] for k in
                                          ("n", "wall_s", "out_tokens", "aggregate_tok_per_s", "request_per_s")}))

print("\nper-request long-run detail:")
for name, rows in DATA.items():
    sel = [r for r in rows if r.get("kind") == "long"]
    print("  %-14s %s" % (name, [(r["ttft_any_ms"], r["total_ms"], r["out_tokens"], r["tok_per_s_total"])
                                 for r in sel]))
