#!/usr/bin/env python3
"""Concurrency A/B: 4 parallel requests per endpoint, run back to back so both
sit in the same provider-load window. Uses ab_cc_vs_opencode for endpoint config."""
import concurrent.futures as cf
import json
import os
import statistics as st
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab_cc_vs_opencode as ab  # noqa: E402

PROMPT = "List the integers from 1 to 250, one per line, no other text."
N = 4


def run(ep):
    ab.apply(ep)

    def one(i):
        r = ab.p.stream_parsed(PROMPT, 1200)
        ab.note(ep, "concurrent_%d" % N, i + 1, r)
        return r

    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=N) as ex:
        results = list(ex.map(one, range(N)))
    wall = time.perf_counter() - t0
    toks = sum(r["out_tokens"] or 0 for r in results)
    rates = [r["tok_per_s_total"] for r in results if r["tok_per_s_total"]]
    agg = toks / wall
    ab.note(ep, "concurrent_summary", N, {"n": N, "wall_s": round(wall, 3), "out_tokens": toks,
                                          "aggregate_tok_per_s": round(agg, 1),
                                          "request_per_s": round(N / wall, 3)})
    print("%-14s N=%d wall=%.2fs per-req tok/s med=%.1f (%.0f-%.0f) aggregate=%.1f tok/s  %.2f req/s"
          % (ep["tag"], N, wall, st.median(rates), min(rates), max(rates), agg, N / wall), flush=True)


for ep in ab.EPS:
    run(ep)
