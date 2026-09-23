# Results: deepseek-v4.1-flash on CommandCode and on OpenCode (Go), Windows re-run

Date: 2026-09-23 (CEST). Machine: Windows 11, Python 3.11.16. Client: `curl` 8.12.1 with a
browser user agent. The two sides ran in the same session, in an interleaved A/B order.

Both routes serve the same model. CommandCode names it `deepseek/deepseek-v4.1-flash`.
OpenCode names it `deepseek-v4.1-flash`.

- CommandCode: 48 clean requests.
- OpenCode (Go): 48 clean requests.
- The phases `transport`, `short`, `long`, `prefill` and `concurrent` ran on both sides.
  Each phase has 3, 20, 16, 1 and 4 samples for a side, plus the concurrent summary.
- The tool reads each token count from the `usage` block of the response. It never counts
  SSE lines.

This campaign repeats the A/B test of the first campaign (macOS, same date) on a different
host. The purpose is to find out whether the difference between the two routes depends on
the machine.

## Comparison of the two routes

The table gives the median value of each measurement.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TLS handshake, new connection | 42.0 ms | 233.8 ms | 5.6 times |
| TTFB of `/models`, new connection | 70.8 ms | 507.9 ms | 7.2 times |
| TTFB of `/models`, reused connection | 21.3 ms | 250.7 ms | 11.8 times |
| Short answer: TTFT of the first token | 844.0 ms | 1474.4 ms | 1.75 times |
| Short answer: TTFT of the visible token | 958.5 ms | 1635.8 ms | 1.71 times |
| Short answer: total time | 963.3 ms | 1694.8 ms | 1.76 times |
| Long answer: TTFT of the first token | 802.0 ms | 1811.3 ms | 2.26 times |
| Long answer: TTFT of the visible token | 1204.1 ms | 2843.3 ms | 2.36 times |
| Long answer: total time | 2375.4 ms | 4604.1 ms | 1.94 times |
| TPS of the sustained decoding | 378.0 tokens/s | 234.1 tokens/s | 0.62 |
| TPS of the visible content | 438.9 tokens/s | 276.1 tokens/s | 0.63 |
| TTFT with 18037 input tokens | 1235.6 ms | 1701.7 ms | 1.38 times |
| 4 parallel requests: rate of one request | 379.6 tokens/s | 233.8 tokens/s | 0.62 |
| 4 parallel requests: total rate | 808.6 tokens/s and 1.11 requests/s | 577.3 tokens/s and 0.57 requests/s | 1.40 times |

The ratios below 1 belong to TPS, where a large number is better. CommandCode is faster on
every measurement.

## The conclusion does not depend on the host

The first campaign ran on macOS. This campaign ran on Windows 11, through another network
path. The absolute values differ, but the ratios agree.

| Measurement | macOS: OpenCode / CommandCode | Windows: OpenCode / CommandCode |
|---|---|---|
| TTFB of `/models`, new connection | 9.7 | 7.2 |
| Short answer: TTFT of the first token | 1.71 | 1.75 |
| Long answer: TTFT of the visible token | 2.01 | 2.36 |
| Long answer: total time | 1.85 | 1.94 |
| TPS of the sustained decoding | 0.64 | 0.62 |
| 4 parallel requests: rate of one request | 0.62 | 0.62 |

The gateway overhead of OpenCode is again the largest single difference. With a ready
socket, one request to `/models` needs 250.7 ms on OpenCode and 21.3 ms on CommandCode.
The handshake of the TLS connection adds 233.8 ms against 42.0 ms.

The TPS of the sustained decoding is again about 1.6 times lower on OpenCode
(234.1 tokens/s against 378.0 tokens/s). The gap in the TTFT of a short answer is
630 ms, or 1.75 times.

## Findings of the re-run

- The gateway overhead of OpenCode is stable. The first campaign measured 265 ms with a
  ready socket, this campaign 250.7 ms. CommandCode measured 20 ms and 21.3 ms.
- The queue of OpenCode varies more. The TTFT of a short answer ran from 1025.3 ms to
  5134.9 ms on OpenCode, and from 601.4 ms to 1920.4 ms on CommandCode.
- Four parallel requests do not lower the rate of one request on either route
  (379.6 tokens/s against 378.0 tokens/s on CommandCode, 233.8 against 234.1 on OpenCode).
  The bottleneck holds at 4 parallel requests.
- The aggregate rate of 4 parallel requests is lower than in the first campaign on both
  sides (808.6 against 947.2 tokens/s on CommandCode, 577.3 against 476.0 on OpenCode).
  The number of output tokens of the sample changed, so read this value with care.
- The model always reasons first. The prompt `Reply with exactly: pong` spends 8 to 41
  reasoning tokens before the visible answer on both routes.
- A large input is cheap on both routes. An input of 18037 tokens gave a TTFT of
  1235.6 ms on CommandCode and 1701.7 ms on OpenCode, in the range of a short prompt.

## Limits

- Each measurement has 1 to 20 samples, and the phases `models`, `prefill` and
  `concurrent` have very few. A difference below 10 percent is noise.
- The absolute values of this campaign are not comparable with the macOS campaign,
  because the host, the network path and the window differ. Compare the ratios only.
- The phase `prefill` uses `max_tokens=24`. On CommandCode the model spent all 24 tokens
  on the reasoning, so the response holds no visible token and the value
  `ttft_content_ms` is absent on that side. The value `ttft_any_ms` is correct on both
  sides.
- The value `tok_per_s_visible` has no meaning for an answer of 3 tokens, because the result
  is a large number. The command `report` does not print the value for a phase whose median
  answer holds fewer than 10 content tokens, so the `short` phase of this campaign has no
  value. Read this value for long answers only.
- The campaign did not test retries, tool calls, or streaming with tools.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_commandcode_20260923T153444Z.json` | 2026-09-23T15:34:44Z | The Windows A/B test, CommandCode side, with 48 records in the `{meta, records}` format. |
| `ab_opencode-go_20260923T153444Z.json` | 2026-09-23T15:34:44Z | The Windows A/B test, OpenCode (Go) side, with 48 records in the `{meta, records}` format. |

Both files carry the same time, because one command `bench.py ab` wrote the two sides together. The campaign of macOS is in the directory `../2026-09-23T150937Z/`. Its `summary.md` holds the full characterization of the model.
