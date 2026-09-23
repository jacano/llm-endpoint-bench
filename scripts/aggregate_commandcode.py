#!/usr/bin/env python3
"""Aggregate latency_commandcode.json into per-phase medians (min/max)."""
import json
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
RECS = json.load(open(os.path.join(HERE, "latency_commandcode.json")))


def med(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return None
    return (round(st.median(vals), 1), round(min(vals), 1), round(max(vals), 1), len(vals))


def report(kind, keys):
    rows = [r for r in RECS if r.get("kind") == kind and not r.get("error")]
    if not rows:
        print("%-18s (no clean rows)" % kind)
        return
    print("%-18s n=%d" % (kind, len(rows)))
    for k in keys:
        m = med([r.get(k) for r in rows])
        if m:
            print("    %-20s median %-10s min %-10s max %-10s (n=%d)" % (k, *m))


print("== transport (/models) ==")
for k in ("dns_ms", "tcp_ms", "tls_ms", "ttfb_ms", "total_ms"):
    m = med([r.get(k) for r in RECS if r.get("kind") == "models"])
    if m:
        print("    %-20s median %-8s min %-8s max %-8s (n=%d)" % (k, *m))

print("\n== streaming (exact tokens from usage) ==")
for kind in ("stream_short", "stream_long", "effort_low", "effort_high", "prefill",
             "concurrent_1", "concurrent_4"):
    report(kind, ("ttft_any_ms", "ttft_content_ms", "total_ms", "in_tokens", "out_tokens",
                  "reasoning_tokens", "content_tokens", "tok_per_s_total", "tok_per_s_visible"))

print("\n== non-streaming ==")
for kind in ("tiny", "medium", "tps_nonstream_off", "tps_nonstream_on", "tiny64"):
    report(kind, ("wall_ms", "in_tokens", "out_tokens", "reasoning_tokens"))

print("\n== legacy chunk counting ==")
for kind in ("stream", "think_off", "think_on", "tps_stream_off", "tps_stream_on"):
    report(kind, ("ttft_ms", "total_ms", "gen_ms", "chunks", "chunk_per_s"))

clean = [r for r in RECS if not r.get("error")]
errs = [r for r in RECS if r.get("error")]
print("\ntotal records %d | clean %d | errored %d" % (len(RECS), len(clean), len(errs)))
for r in errs[:5]:
    print("   ERR", r.get("kind"), str(r.get("error"))[:120])
lo = [r for r in RECS if r.get("kind") == "stream_long"]
print("\neffective generation rate check (stream_long):")
for r in lo:
    print("   gen_ms=%s out=%s -> %.1f tok/s" % (r["gen_ms"], r["out_tokens"], r["tok_per_s_total"]))
