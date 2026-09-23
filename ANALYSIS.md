# The analysis of the results

Three campaigns measured the same model, `deepseek-v4.1-flash`, on two routes: CommandCode and
OpenCode (Go). This file holds their tables, what the differences come from, what holds between
the campaigns, and the limits of the measurements.

The raw records and the full tables of each campaign are in `results/`, which `results/README.md`
indexes:

- `results/2026-09-23T150937Z/` — the first campaign, on macOS. It holds the full
  characterization of the model and the first A/B test.
- `results/2026-09-23T153444Z/` — the second campaign, the same A/B test on Windows 11 through
  another network path.
- `results/2026-09-23T204204Z/` — the third campaign, four hours later on the same host, with the
  phase `thinking` added.

The tool that produced them is `bench.py`; the README states it.

## The first campaign (macOS)

CommandCode is faster than OpenCode (Go) on every measurement. The table gives the median value
of each measurement. TTFB (time to the first byte) is the delay before the response starts. TTFT
(time to the first token) is the delay before the model writes the first token.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TTFB of `/models`, new connection | 47 ms | 460 ms | 9.7 times |
| TTFB of `/models`, reused connection | 20 ms | 265 ms | 13 times |
| Short answer: TTFT of the first token | 912 ms | 1561 ms | 1.71 times |
| Short answer: total time | 1046 ms | 1792 ms | 1.71 times |
| Long answer of 620 tokens: TTFT of the first visible token | 1511 ms | 3033 ms | 2.01 times |
| Long answer of 620 tokens: total time | 2673 ms | 4948 ms | 1.85 times |
| TPS of the sustained decoding | 360 tokens/s | 230 tokens/s | 0.64 |
| TPS of the visible content | 439 tokens/s | 260 tokens/s | 0.59 |
| TTFT with 18000 input tokens | 1671 ms | 3774 ms | 2.26 times |
| 4 parallel requests: rate of one request | 378 tokens/s | 233 tokens/s | 0.62 |
| 4 parallel requests: total rate | 947 tokens/s | 476 tokens/s | 0.50 |
| 4 parallel requests: requests each second | 1.66 | 0.81 | 0.49 |

A ratio above 1 belongs to a delay; a ratio below 1 belongs to a rate, where a large number is
better.

Both routes serve the same model, so the infrastructure makes the difference. The gateway of
OpenCode adds about 245 ms to each request with a ready socket, which is about 13 times the cost
of CommandCode. OpenCode also decodes 1.6 times slower in the steady state.

## The second campaign (Windows 11)

The same A/B test ran again on a Windows 11 host through another network path. The absolute
values differ, but the ratios agree with the first campaign. The full tables are in
`results/2026-09-23T153444Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TTFB of `/models`, reused connection | 21.3 ms | 250.7 ms | 11.8 times |
| Short answer: TTFT of the first token | 844.0 ms | 1474.4 ms | 1.75 times |
| Long answer of 500 visible tokens: TTFT of the first visible token | 1204.1 ms | 2843.3 ms | 2.36 times |
| TPS of the sustained decoding | 378.0 tokens/s | 234.1 tokens/s | 0.62 |
| 4 parallel requests: total rate | 808.6 tokens/s | 577.3 tokens/s | 0.71 |

A ratio below 1 belongs to a rate, where a large number is better.

The conclusion does not depend on the host: CommandCode is faster on every measurement in both
campaigns.

## The third campaign (Windows 11, a second window)

The same A/B test ran a second time on the same Windows 11 host, four hours after the second
campaign, and it added the phase `thinking`. Every difference points the same way; the size of a
difference moves with the queue of the provider. The full tables are in
`results/2026-09-23T204204Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TTFB of `/models`, reused connection | 32.0 ms | 291.6 ms | 9.11 |
| Short answer: TTFT of the first token | 812.5 ms | 1784.8 ms | 2.20 |
| Long answer of 500 visible tokens: TTFT of the first visible token | 1462.2 ms | 2429.8 ms | 1.66 |
| TPS of the sustained decoding | 372.1 tokens/s | 234.2 tokens/s | 0.63 |
| 4 parallel requests: total rate | 799.7 tokens/s | 478.8 tokens/s | 0.60 |

## What holds between the campaigns

The direction of every difference is the same in all three campaigns. The size of a difference
moves with the queue of the provider, and two families of measurement move differently.

| OpenCode divided by CommandCode | macOS, 15:09 | Windows, 15:34 | Windows, 20:42 |
|---|---|---|---|
| TTFB of `/models`, reused connection | 13.0 | 11.77 | 9.11 |
| Short answer: TTFT of the first token | 1.71 | 1.75 | 2.20 |
| Long answer: TTFT of the visible token | 2.01 | 2.36 | 1.66 |
| Long answer: total time | 1.85 | 1.94 | 1.66 |
| TPS of the sustained decoding | 0.64 | 0.62 | 0.63 |
| 4 parallel requests: rate of one request | 0.62 | 0.62 | 0.63 |

- The rate of the sustained decoding is the most stable value of the three campaigns: 0.64, 0.62
  and 0.63. The same holds for the rate of one request under 4 parallel requests: 0.62, 0.62 and
  0.63.
- The ratios of the delays move between windows: the gap in the TTFT of a short answer went from
  1.75 to 2.20 between the two runs on the same host, and the gap in the long answer went from
  2.36 to 1.66. A fixed cost of the gateway plus a varying queue explains both.
- The gateway overhead of OpenCode is stable in absolute terms: 265 ms, 250.7 ms and 291.6 ms
  with a ready socket, against 20 ms, 21.3 ms and 32.0 ms on CommandCode.
- The phase `prefill` shows that a large input is cheap on both routes: an input of about 18000
  tokens gave a TTFT in the range of a short prompt.
- The reasoning controls do not hold the model back. `thinking: {"type": "disabled"}` did not
  stop the reasoning on CommandCode, and `thinking: enabled` spent the whole budget of the phase
  on the reasoning on both routes.

## Limits

Each campaign ran for about 10 minutes on one machine. Each measurement has 1 to 20 samples, and
the table of a comparison prints the number of samples of each side, so a phase with one sample
shows a ratio without a verdict. A difference below 10 percent is noise. The queue of the provider
changes between windows: the TTFT of one endpoint went from 620 ms to 2660 ms for the same prompt.
The absolute values of two campaigns are not comparable, because the host, the network path and
the window differ; compare the ratios only. The campaign did not test retries, tool calls, or
streaming with tools. A measurement becomes stale, so measure again before you change a route or a
budget.

The `summary.md` of each campaign states the limits of that campaign, including the phases of it
that hold too few tokens for a rate.
