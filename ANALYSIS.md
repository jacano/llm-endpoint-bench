# The analysis of the results

Three campaigns measured the same model, `deepseek-v4.1-flash`, on two routes, CommandCode and
OpenCode (Go), on one Windows 11 host, twenty minutes to four hours apart. This file holds their
tables, what the differences come from, what holds between the windows, and the limits of the
measurements.

The raw records and the full tables of each campaign are in `results/`, which `results/README.md`
indexes:

- `results/2026-09-23T153444Z/` — the first window.
- `results/2026-09-23T204204Z/` — the second window, four hours later.
- `results/2026-09-23T210256Z/` — the third window, twenty minutes after the second one.

The tool that produced them is `bench.py`; the README states it.

## The first window (15:34Z)

CommandCode is faster than OpenCode (Go) on every measurement. The table gives the median value of
each measurement: TTFB is the delay before the response starts, and TTFT the delay before the
model writes the first token. The full tables are in `results/2026-09-23T153444Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TLS handshake, new connection | 42.0 ms | 233.8 ms | 5.6 |
| TTFB of `/models`, new connection | 70.8 ms | 507.9 ms | 7.2 |
| TTFB of `/models`, reused connection | 21.3 ms | 250.7 ms | 11.8 |
| Short answer: TTFT of the first token | 844.0 ms | 1474.4 ms | 1.75 |
| Long answer: TTFT of the visible token | 1204.1 ms | 2843.3 ms | 2.36 |
| Long answer: total time | 2375.4 ms | 4604.1 ms | 1.94 |
| TPS of the sustained decoding | 378.0 tokens/s | 234.1 tokens/s | 0.62 |
| TPS of the visible content | 438.9 tokens/s | 276.1 tokens/s | 0.63 |
| 4 parallel requests: rate of one request | 379.6 tokens/s | 233.8 tokens/s | 0.62 |
| 4 parallel requests: total rate | 808.6 tokens/s | 577.3 tokens/s | 0.71 |

A ratio above 1 belongs to a delay; a ratio below 1 belongs to a rate, where a large number is
better.

## The second window (20:42Z)

The same A/B test ran again on the same host, four hours later. Every difference points the same
way; the size of a difference moves with the queue of the provider. The full tables are in
`results/2026-09-23T204204Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TLS handshake, new connection | 38.6 ms | 247.9 ms | 6.42 |
| TTFB of `/models`, reused connection | 32.0 ms | 291.6 ms | 9.11 |
| Short answer: TTFT of the first token | 812.5 ms | 1784.8 ms | 2.20 |
| Long answer of 500 visible tokens: TTFT of the first visible token | 1462.2 ms | 2429.8 ms | 1.66 |
| Long answer of 500 visible tokens: total time | 2610.4 ms | 4337.5 ms | 1.66 |
| TPS of the sustained decoding | 372.1 tokens/s | 234.2 tokens/s | 0.63 |
| TPS of the visible content | 442.8 tokens/s | 260.4 tokens/s | 0.59 |
| 4 parallel requests: rate of one request | 377.6 tokens/s | 239.7 tokens/s | 0.63 |
| 4 parallel requests: total rate | 799.7 tokens/s | 478.8 tokens/s | 0.60 |

## The third window (21:02Z)

The same A/B test ran a third time on the same host, twenty minutes after the second window. Every
difference points the same way, and the delays of the model itself stayed inside the range of the
windows before it. The full tables are in `results/2026-09-23T210256Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TLS handshake, new connection | 37.9 ms | 230.0 ms | 6.07 |
| TTFB of `/models`, reused connection | 15.8 ms | 325.2 ms | 20.58 |
| Short answer: TTFT of the first token | 826.3 ms | 1781.7 ms | 2.16 |
| Long answer of 500 visible tokens: TTFT of the first visible token | 1380.4 ms | 2699.5 ms | 1.96 |
| Long answer of 500 visible tokens: total time | 2503.9 ms | 4645.6 ms | 1.86 |
| TPS of the sustained decoding | 373.1 tokens/s | 246.7 tokens/s | 0.66 |
| TPS of the visible content | 446.3 tokens/s | 273.4 tokens/s | 0.61 |
| 4 parallel requests: rate of one request | 360.5 tokens/s | 217.7 tokens/s | 0.60 |
| 4 parallel requests: total rate | 866.2 tokens/s | 429.5 tokens/s | 0.50 |

## What holds between the windows

The direction of every difference is the same in all three windows. The size of a difference moves
with the queue of the provider, and two families of measurement move differently.

| OpenCode divided by CommandCode | 15:34 | 20:42 | 21:02 |
|---|---|---|---|
| TTFB of `/models`, reused connection | 11.77 | 9.11 | 20.58 |
| Short answer: TTFT of the first token | 1.75 | 2.20 | 2.16 |
| Long answer: TTFT of the visible token | 2.36 | 1.66 | 1.96 |
| Long answer: total time | 1.94 | 1.66 | 1.86 |
| TPS of the sustained decoding | 0.62 | 0.63 | 0.66 |
| 4 parallel requests: rate of one request | 0.62 | 0.63 | 0.60 |

- The rate of the sustained decoding is the most stable value of the three windows: 0.62, 0.63 and
  0.66. The same holds for the rate of one request under 4 parallel requests: 0.62, 0.63 and 0.60.
- The ratios of the delays move between windows: the gap in the TTFT of a short answer went from
  1.75 to 2.20 between the first two windows, and the gap in the long answer from 2.36 to 1.66. A
  fixed cost of the gateway plus a varying queue explains both.
- The row of the reused socket is the least stable of the table, 9.11 to 20.58, and the third
  window moved both sides at once: the median TTFB on a ready socket fell to 15.8 ms on
  CommandCode while it rose to 325.2 ms on OpenCode. Read that row as the cost of the gateway at a
  moment, not as a property of the route.
- The gateway overhead of OpenCode is stable in absolute terms: 250.7 ms, 291.6 ms and 325.2 ms
  with a ready socket, against 21.3 ms, 32.0 ms and 15.8 ms on CommandCode.
- 4 parallel requests do not lower the rate of one request on either route in any window. The
  aggregate rate is about twice the rate of one request on both sides, so the bottleneck of both
  routes holds at 4 parallel requests.
- The model always reasons first, in every window: the prompt `Reply with exactly: pong` spends
  about 10 reasoning tokens before the visible answer of 3 tokens, on both routes.

## Limits

Each campaign ran for about 10 minutes on one machine. Each measurement has 1 to 20 samples, and
the table of a comparison prints the number of samples of each side, so a phase of one sample shows
a ratio without a verdict. A difference below 10 percent is noise. The queue of the provider
changes between windows: the TTFT of one endpoint went from 620 ms to 2660 ms for the same prompt.
The absolute values of two campaigns are not comparable, because the host, the network path and the
window differ; compare the ratios only. The campaign did not test retries, tool calls, or streaming
with tools. A measurement becomes stale, so measure again before you change a route or a budget.

The `summary.md` of each campaign states the limits of that campaign, including the phases of it
that hold too few tokens for a rate.
