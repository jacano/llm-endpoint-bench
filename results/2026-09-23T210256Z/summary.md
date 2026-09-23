# Results: deepseek-v4.1-flash on CommandCode and on OpenCode (Go), a third run on Windows 11

The run started at 2026-09-23T21:02:56Z (23:02 local time). Machine: Windows 11, Python 3.11.16.
Client: `curl` 8.12.1 with a browser user agent. The two sides ran in the same session, in an
interleaved A/B order.

Both routes serve the same model. CommandCode names it `deepseek/deepseek-v4.1-flash`. OpenCode
names it `deepseek-v4.1-flash`.

- CommandCode: 54 clean requests, no error.
- OpenCode (Go): 54 clean requests, no error.
- The phases `transport`, `short`, `long`, `prefill`, `thinking` and `concurrent` ran on both
  sides. Each phase has 3, 20, 16, 1, 5 and 4 samples for a side, plus the concurrent summary.
- The tool reads each token count from the `usage` block of the response.

This is the fourth campaign and the third one on this host. It repeats the A/B test of the runs
of 15:34:44Z and 20:42:04Z on the same machine, 20 minutes after the second of them, in another
window of the provider. The command was the same:

```
python bench.py ab --a commandcode --b opencode-go \
  --phases transport,short,long,prefill,thinking,concurrent --n 4 --concurrent 4
```

## Comparison of the two routes

The table gives the median value of each measurement.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TLS handshake, new connection | 37.9 ms | 230.0 ms | 6.07 |
| TTFB of `/models`, new connection | 61.2 ms | 516.0 ms | 8.43 |
| TTFB of `/models`, reused connection | 15.8 ms | 325.2 ms | 20.58 |
| Short answer: TTFT of the first token | 826.3 ms | 1781.7 ms | 2.16 |
| Short answer: TTFT of the visible token | 919.9 ms | 1913.8 ms | 2.08 |
| Short answer: total time | 923.5 ms | 1924.2 ms | 2.08 |
| Long answer: TTFT of the first token | 908.8 ms | 1832.5 ms | 2.02 |
| Long answer: TTFT of the visible token | 1380.4 ms | 2699.5 ms | 1.96 |
| Long answer: total time | 2503.9 ms | 4645.6 ms | 1.86 |
| TPS of the sustained decoding | 373.1 tokens/s | 246.7 tokens/s | 0.66 |
| TPS of the visible content | 446.3 tokens/s | 273.4 tokens/s | 0.61 |
| TTFT with 18037 input tokens | 1227.4 ms | 2057.1 ms | 1.68 |
| 4 parallel requests: rate of one request | 360.5 tokens/s | 217.7 tokens/s | 0.60 |
| 4 parallel requests: total rate | 866.2 tokens/s and 1.5 requests/s | 429.5 tokens/s and 0.6 requests/s | 0.50 |

A ratio below 1 belongs to a rate, where a large number is better. CommandCode is faster on
every measurement.

## The ratios hold, the absolute values move

The same test has now run three times on this host and once on a macOS host. The direction of
every difference is the same in all four campaigns. The size of a difference moves with the
queue of the provider, and two families of measurement move differently.

| Measurement: OpenCode divided by CommandCode | 2026-09-23T150937Z, macOS | 2026-09-23T153444Z, Windows | 2026-09-23T204204Z, Windows | 2026-09-23T210256Z, Windows |
|---|---|---|---|---|
| TTFB of `/models`, reused connection | 13.0 | 11.77 | 9.11 | 20.58 |
| Short answer: TTFT of the first token | 1.71 | 1.75 | 2.20 | 2.16 |
| Long answer: TTFT of the visible token | 2.01 | 2.36 | 1.66 | 1.96 |
| Long answer: total time | 1.85 | 1.94 | 1.66 | 1.86 |
| TPS of the sustained decoding | 0.64 | 0.62 | 0.63 | 0.66 |
| 4 parallel requests: rate of one request | 0.62 | 0.62 | 0.63 | 0.60 |

- The rate of the sustained decoding is the most stable value of the four campaigns: 0.64, 0.62,
  0.63 and 0.66. The same holds for the rate of one request under 4 parallel requests: 0.62, 0.62,
  0.63 and 0.60.
- The ratio of the reused socket moved further than in any other window, and both sides caused it:
  the median TTFB of `/models` on a ready socket fell to 15.8 ms on CommandCode (21.3 ms and
  32.0 ms in the two windows before) while it rose to 325.2 ms on OpenCode (250.7 ms and
  291.6 ms). A row of this kind is worth less than a row of a rate: read it as the cost of the
  gateway at a moment, not as a property of the route.
- The ratios of the delays of the model itself stayed inside the range of the other windows: the
  short answer at 2.16 against 1.75 to 2.20, the long answer at 1.96 against 1.66 to 2.36.

## Cause of the difference

The gateway of OpenCode adds a fixed cost to each request. With a ready socket, one request to
`/models` needs 325.2 ms on OpenCode and 15.8 ms on CommandCode. The handshake of a new TLS
connection adds 230.0 ms against 37.9 ms.

The rest of the gap comes from the queue and the start of the model. OpenCode serves the same
model about 1.5 times slower in the sustained decoding, on the same output: the two sides wrote
631.5 and 601.5 output tokens for the long answer, a difference of 5 percent.

## The reasoning controls do not hold the model back

The phase `thinking` sends one long answer under each control. The table gives the value of one
request for each control, so it is an observation and not a measurement.

| Control | CommandCode: reasoning tokens | OpenCode (Go): reasoning tokens |
|---|---|---|
| absent | 63 | 102 |
| `thinking: disabled` | 36 | 0 |
| `thinking: enabled` | 110 | 57 |
| `reasoning_effort: low` | 81 | 124 |
| `reasoning_effort: high` | 206 | 130 |

The value `thinking: {"type": "disabled"}` did not stop the reasoning on CommandCode, which spent
36 reasoning tokens. On OpenCode the same control gave a report of 0 reasoning tokens, and that
side spent the whole budget of the phase on the content of the answer instead. The value
`thinking: enabled` spent 110 and 57 reasoning tokens, where the same control spent the whole
budget of 400 tokens on both routes in the run of 20:42:04Z: the count of reasoning tokens of one
long answer is not a property of the control, and one request proves nothing in either direction.
Read this phase as a hint that the routes do not treat these parameters in the same way.

## Parallel requests

| Endpoint | One request | 4 parallel requests, total | Requests each second |
|---|---|---|---|
| CommandCode | 360.5 tokens/s | 866.2 tokens/s | 1.5 |
| OpenCode (Go) | 217.7 tokens/s | 429.5 tokens/s | 0.6 |

Four parallel requests do not lower the rate of one request on either route: the aggregate rate
is about twice the rate of one request on both sides, which is the same finding as in the two
windows before. The bottleneck of both routes holds at 4 parallel requests.

## Limits

- Each measurement has 1 to 20 samples, and the phases `models`, `prefill`, `thinking` and
  `concurrent` have very few. A difference below 10 percent is noise. The comparison prints the
  number of samples of each side and names no winner for a phase with fewer than 3.
- The absolute values of this campaign are not comparable with the other campaigns, because the
  host, the network path and the window differ. Compare the ratios only.
- The absolute values of a ratio of a delay are not comparable between rows either: the row of
  the reused socket is the least stable of the table, 13.0 to 20.58 over four campaigns. The rate
  of the sustained decoding is the most stable, 0.60 to 0.66.
- The phase `prefill` uses `max_tokens=24`. On CommandCode the model spent all 24 tokens on the
  reasoning, so the response holds no visible token and the value `ttft_content_ms` is absent on
  that side. On OpenCode the answer held 2 content tokens, so the record holds a rate of 107526.9
  tokens/s that the tool does not print: a rate needs an answer of 50 output tokens behind it.
  The value `ttft_any_ms` is correct on both sides.
- A rate needs a numerator. The tool prints no rate for a phase whose median answer holds fewer
  than 50 output tokens or fewer than 10 content tokens, so the `short` and `prefill` phases of
  this campaign hold no rate at all, and the five phases of `thinking` hold none of
  `tok_per_s_visible`. Read a rate for long answers only.
- The number of model identifiers that a route lists is a count, not a score: CommandCode lists
  80 and OpenCode lists 35 in this window.
- The campaign did not test retries, tool calls, or streaming with tools.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_commandcode_20260923T210256Z.json` | 2026-09-23T21:02:56Z | This A/B test, CommandCode side, with 54 records in the `{meta, records}` format. |
| `ab_opencode-go_20260923T210256Z.json` | 2026-09-23T21:02:56Z | This A/B test, OpenCode (Go) side, with 54 records in the `{meta, records}` format. |

Both files carry the same time, because one command `bench.py ab` wrote the two sides together.
The earlier campaigns are in the directories `../2026-09-23T150937Z/` (macOS, with the full
characterization of the model), `../2026-09-23T153444Z/` (Windows, the first run) and
`../2026-09-23T204204Z/` (Windows, the second run).
