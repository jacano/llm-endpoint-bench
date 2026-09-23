# Results: deepseek-v4.1-flash on CommandCode and on OpenCode (Go), Windows 11, 20:42Z

The run started at 2026-09-23T20:42:04Z (22:42 local time). Machine: Windows 11, Python 3.11.16.
Client: `curl` 8.12.1 with a browser user agent. The two sides ran in the same session, in an
interleaved A/B order.

Both routes serve the same model. CommandCode names it `deepseek/deepseek-v4.1-flash`. OpenCode
names it `deepseek-v4.1-flash`.

- CommandCode: 48 clean requests, no error.
- OpenCode (Go): 48 clean requests, no error.
- The phases `transport`, `short`, `long` and `concurrent` ran on both sides. Each phase has 3,
  20, 16 and 4 samples for a side, plus the concurrent summary.
- The tool reads each token count from the `usage` block of the response.

This is the second window on this host. It repeats the A/B test of the run of 15:34:44Z on the
same machine, four hours later, in a different window of the provider.

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
| 4 parallel requests: rate of one request | 377.6 tokens/s | 239.7 tokens/s | 0.63 |
| 4 parallel requests: total rate | 799.7 tokens/s and 1.41 requests/s | 478.8 tokens/s and 0.57 requests/s | 0.60 |

A ratio below 1 belongs to a rate, where a large number is better. CommandCode is faster on
every measurement.

## The ratios hold, the absolute values move

The same test ran three times on this host, twenty minutes to four hours apart. The direction of
every difference is the same; the size of a difference moves with the queue of the provider.

| Measurement: OpenCode divided by CommandCode | 2026-09-23T153444Z | 2026-09-23T204204Z | 2026-09-23T210256Z |
|---|---|---|---|
| TTFB of `/models`, reused connection | 11.77 | 9.11 | 20.58 |
| Short answer: TTFT of the first token | 1.75 | 2.20 | 2.16 |
| Long answer: TTFT of the visible token | 2.36 | 1.66 | 1.96 |
| Long answer: total time | 1.94 | 1.66 | 1.86 |
| TPS of the sustained decoding | 0.62 | 0.63 | 0.66 |
| 4 parallel requests: rate of one request | 0.62 | 0.63 | 0.60 |

The rate of the sustained decoding is the most stable value of the three windows: 0.62, 0.63 and
0.66. The gap in the TTFT of a short answer moved from 1.75 to 2.20 between the two windows of
this host, and the aggregate rate of 4 parallel requests moved from 0.71 to 0.50. Both values
depend on the queue at the moment of the request.

## Cause of the difference

The gateway of OpenCode adds a fixed cost to each request, and the network does not cause all
of it. With a ready socket, one request to `/models` needs 291.6 ms on OpenCode and 32.0 ms on
CommandCode. The handshake of a new TLS connection adds 247.9 ms against 38.6 ms.

The rest of the gap comes from the queue and the start of the model. OpenCode serves the same
model about 1.6 times slower in the sustained decoding, on the same output.

## Parallel requests

| Endpoint | One request | 4 parallel requests, total | Requests each second |
|---|---|---|---|
| CommandCode | 377.6 tokens/s | 799.7 tokens/s | 1.41 |
| OpenCode (Go) | 239.7 tokens/s | 478.8 tokens/s | 0.57 |

Four parallel requests do not lower the rate of one request on either route. The bottleneck of
both routes holds at 4 parallel requests.

## Limits

- Each measurement has 1 to 20 samples, and the phases `models` and `concurrent` have 3 and 4
  samples for a side. A difference below 10 percent is noise. The comparison prints the number of
  samples of each side and names no winner for a phase of one sample.
- The absolute values of this campaign are not comparable with those of another window, because
  the host, the network path and the window differ. Compare the ratios only.
- A rate needs a numerator. The tool prints no rate for a phase whose median answer holds fewer
  than 50 output tokens or fewer than 10 content tokens, so the `short` phase of this campaign
  holds no rate. Read a rate for long answers only.
- The campaign did not test retries, tool calls, or streaming with tools.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_commandcode_20260923T204204Z.json` | 2026-09-23T20:42:04Z | This A/B test, CommandCode side, with 48 records in the `{meta, records}` format. |
| `ab_opencode-go_20260923T204204Z.json` | 2026-09-23T20:42:04Z | This A/B test, OpenCode (Go) side, with 48 records in the `{meta, records}` format. |

Both files carry the same time, because one command `bench.py ab` wrote the two sides together.
The other two windows of this host are in the directories `../2026-09-23T153444Z/` (the first) and
`../2026-09-23T210256Z/` (the third).
