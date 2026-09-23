#!/usr/bin/env python3
"""Concurrency check: does per-request decode rate degrade when N requests run in parallel?

Run: python probe_concurrent.py [N]
"""
import concurrent.futures as cf
import sys
import time

sys.path.insert(0, ".")
import probe_cc_v2 as p  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
PROMPT = "List the integers from 1 to 250, one per line, no other text."


def one(i):
    r = p.stream_parsed(PROMPT, 1200)
    p.rec(kind="concurrent_%d" % N, iter=i + 1, **r)
    return r


t0 = time.perf_counter()
with cf.ThreadPoolExecutor(max_workers=N) as ex:
    results = list(ex.map(one, range(N)))
wall = time.perf_counter() - t0

toks = [r["out_tokens"] or 0 for r in results]
rates = [r["tok_per_s_total"] for r in results if r["tok_per_s_total"]]
print("N=%d wall=%.2fs" % (N, wall))
for i, r in enumerate(results, 1):
    print("  req%d ttft_any=%s ttft_content=%s total=%s out=%s tok/s=%s"
          % (i, r["ttft_any_ms"], r["ttft_content_ms"], r["total_ms"], r["out_tokens"], r["tok_per_s_total"]))
print("per-request tok/s: %s (max %.1f)" % ([round(x, 1) for x in rates], max(rates) if rates else 0))
print("aggregate tok/s (sum tokens / wall): %.1f" % (sum(toks) / wall))
print("aggregate req/s: %.3f" % (N / wall))
p.rec(kind="concurrent_summary", n=N, wall_s=round(wall, 3), total_out_tokens=sum(toks),
      aggregate_tok_per_s=round(sum(toks) / wall, 1), request_per_s=round(N / wall, 3))
