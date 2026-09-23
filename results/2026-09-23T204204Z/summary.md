# Results: deepseek-v4.1-flash on CommandCode and on OpenCode (Go), a second run on Windows 11

The run started at 2026-09-23T20:42:04Z (22:42 local time). Machine: Windows 11, Python 3.11.16.
Client: `curl` 8.12.1 with a browser user agent. The two sides ran in the same session, in an
interleaved A/B order.

Both routes serve the same model. CommandCode names it `deepseek/deepseek-v4.1-flash`. OpenCode
names it `deepseek-v4.1-flash`.

- CommandCode: 54 clean requests, no error.
- OpenCode (Go): 54 clean requests, no error.
- The phases `transport`, `short`, `long`, `prefill`, `thinking` and `concurrent` ran on both
  sides. Each phase has 3, 20, 16, 1, 5 and 4 samples for a side, plus the concurrent summary.
- The tool reads each token count from the `usage` block of the response.

This is the third campaign and the second one on this host. It repeats the A/B test of the run
of 15:34:44Z on the same machine, four hours later, in a different window of the provider.

## Comparison of the two routes

The table gives the median value of each measurement.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TLS handshake, new connection | 38.6 ms | 247.9 ms | 6.42 |
| TTFB of `/models`, new connection | 74.0 ms | 496.5 ms | 6.71 |
| TTFB of `/models`, reused connection | 32.0 ms | 291.6 ms | 9.11 |
| Short answer: TTFT of the first token | 812.5 ms | 1784.8 ms | 2.20 |
| Short answer: TTFT of the visible token | 924.5 ms | 1871.0 ms | 2.02 |
| Short answer: total time | 931.1 ms | 1895.8 ms | 2.04 |
| Long answer: TTFT of the first token | 946.2 ms | 1769.4 ms | 1.87 |
| Long answer: TTFT of the visible token | 1462.2 ms | 2429.8 ms | 1.66 |
| Long answer: total time | 2610.4 ms | 4337.5 ms | 1.66 |
| TPS of the sustained decoding | 372.1 tokens/s | 234.2 tokens/s | 0.63 |
| TPS of the visible content | 442.8 tokens/s | 260.4 tokens/s | 0.59 |
| TTFT with 18037 input tokens | 1503.7 ms | 2330.4 ms | 1.55 |
| 4 parallel requests: rate of one request | 377.6 tokens/s | 239.7 tokens/s | 0.63 |
| 4 parallel requests: total rate | 799.7 tokens/s and 1.41 requests/s | 478.8 tokens/s and 0.57 requests/s | 0.60 |

A ratio below 1 belongs to a rate, where a large number is better. CommandCode is faster on
every measurement.

## The ratios hold, the absolute values move

The same test ran twice on this host, four hours apart. The direction of every difference is
the same; the size of the difference moves with the queue of the provider.

| Measurement: OpenCode divided by CommandCode | 2026-09-23T150937Z, macOS | 2026-09-23T153444Z, Windows | 2026-09-23T204204Z, Windows |
|---|---|---|---|
| TTFB of `/models`, reused connection | 13.0 | 11.77 | 9.11 |
| Short answer: TTFT of the first token | 1.71 | 1.75 | 2.20 |
| Long answer: TTFT of the visible token | 2.01 | 2.36 | 1.66 |
| Long answer: total time | 1.85 | 1.94 | 1.66 |
| TPS of the sustained decoding | 0.64 | 0.62 | 0.63 |
| 4 parallel requests: rate of one request | 0.62 | 0.62 | 0.63 |

The rate of the sustained decoding is the most stable value of the three campaigns: 0.64, 0.62
and 0.63. The gap in the TTFT of a short answer moved from 1.75 to 2.20 between the two runs on
this host, and the aggregate rate of 4 parallel requests moved from 0.71 to 0.60. Both values
depend on the queue at the moment of the request.

## Cause of the difference

The gateway of OpenCode adds a fixed cost to each request, and the network does not cause all
of it. With a ready socket, one request to `/models` needs 291.6 ms on OpenCode and 32.0 ms on
CommandCode. The handshake of a new TLS connection adds 247.9 ms against 38.6 ms.

The rest of the gap comes from the queue and the start of the model. OpenCode serves the same
model about 1.6 times slower in the sustained decoding, on the same output.

## The reasoning controls do not hold the model back

The phase `thinking` sends one long answer under each control. The table gives the value of one
request for each control, so it is an observation and not a measurement.

| Control | CommandCode: reasoning tokens | OpenCode (Go): reasoning tokens |
|---|---|---|
| absent | 52 | 62 |
| `thinking: disabled` | 130 | 0 |
| `thinking: enabled` | 400 (the whole budget) | 400 (the whole budget) |
| `reasoning_effort: low` | 400 (the whole budget) | 94 |
| `reasoning_effort: high` | 101 | 92 |

The value `thinking: {"type": "disabled"}` did not stop the reasoning on CommandCode, which
spent 130 reasoning tokens. On OpenCode the same control gave a report of 0 reasoning tokens,
but that side spent its budget on the content of the answer instead. The value
`thinking: enabled` spent the whole budget of 400 tokens on the reasoning on both routes, and
so did `reasoning_effort: low` on CommandCode. One request proves nothing, because the count of
reasoning tokens of a long answer changes between requests in any case. Read this phase as a
hint that the routes do not treat these parameters in the same way.

## Parallel requests

| Endpoint | One request | 4 parallel requests, total | Requests each second |
|---|---|---|---|
| CommandCode | 377.6 tokens/s | 799.7 tokens/s | 1.41 |
| OpenCode (Go) | 239.7 tokens/s | 478.8 tokens/s | 0.57 |

Four parallel requests do not lower the rate of one request on either route. The bottleneck of
both routes holds at 4 parallel requests.

## Limits

- Each measurement has 1 to 20 samples, and the phases `models`, `prefill`, `thinking` and
  `concurrent` have very few. A difference below 10 percent is noise.
- The absolute values of this campaign are not comparable with the other campaigns, because the
  host, the network path and the window differ. Compare the ratios only.
- The phase `prefill` uses `max_tokens=24`. On CommandCode the model spent all 24 tokens on the
  reasoning, so the response holds no visible token and the value `ttft_content_ms` is absent on
  that side. On OpenCode the answer held 2 content tokens, so the record holds a rate of 104712
  tokens/s that the tool does not print: a rate needs an answer of 50 output tokens behind it.
  The value `ttft_any_ms` is correct on both sides.
- A rate needs a numerator. The tool prints no rate for a phase whose median answer holds fewer
  than 50 output tokens or fewer than 10 content tokens, so the `short` and `prefill` phases of
  this campaign hold no rate at all, and `thinking_enabled` and `thinking_effort_low` hold none
  of `tok_per_s_visible`. Read a rate for long answers only.
- The campaign did not test retries, tool calls, or streaming with tools.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_commandcode_20260923T204204Z.json` | 2026-09-23T20:42:04Z | This A/B test, CommandCode side, with 54 records in the `{meta, records}` format. |
| `ab_opencode-go_20260923T204204Z.json` | 2026-09-23T20:42:04Z | This A/B test, OpenCode (Go) side, with 54 records in the `{meta, records}` format. |

Both files carry the same time, because one command `bench.py ab` wrote the two sides together.
The earlier campaigns are in the directories `../2026-09-23T150937Z/` (macOS, with the full
characterization of the model) and `../2026-09-23T153444Z/` (Windows, the first run).
