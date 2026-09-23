# Results: deepseek-v4.1-flash on CommandCode and on OpenCode (Go), Windows 11, 21:02Z

The run started at 2026-09-23T21:02:56Z (23:02 local time). Machine: Windows 11, Python 3.11.16.
Client: `curl` 8.12.1 with a browser user agent. The two sides ran in the same session, in an
interleaved A/B order.

Both routes serve the same model. CommandCode names it `deepseek/deepseek-v4.1-flash`. OpenCode
names it `deepseek-v4.1-flash`.

- CommandCode: 48 clean requests, no error.
- OpenCode (Go): 48 clean requests, no error.
- The phases `transport`, `short`, `long` and `concurrent` ran on both sides. Each phase has 3,
  20, 16 and 4 samples for a side, plus the concurrent summary.
- The tool reads each token count from the `usage` block of the response.

This is the third window on this host. It repeats the A/B test of the runs of 15:34:44Z and
20:42:04Z on the same machine, twenty minutes after the second of them, in another window of the
provider. The command was:

```
python bench.py ab --a commandcode --b opencode-go --n 4
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
| 4 parallel requests: rate of one request | 360.5 tokens/s | 217.7 tokens/s | 0.60 |
| 4 parallel requests: total rate | 866.2 tokens/s and 1.5 requests/s | 429.5 tokens/s and 0.6 requests/s | 0.50 |

A ratio below 1 belongs to a rate, where a large number is better. CommandCode is faster on
every measurement.

## The ratios hold, the absolute values move

The same test has now run three times on this host. The direction of every difference is the same
in all three windows, and the size of a difference moves with the queue of the provider.

| Measurement: OpenCode divided by CommandCode | 2026-09-23T153444Z | 2026-09-23T204204Z | 2026-09-23T210256Z |
|---|---|---|---|
| TTFB of `/models`, reused connection | 11.77 | 9.11 | 20.58 |
| Short answer: TTFT of the first token | 1.75 | 2.20 | 2.16 |
| Long answer: TTFT of the visible token | 2.36 | 1.66 | 1.96 |
| Long answer: total time | 1.94 | 1.66 | 1.86 |
| TPS of the sustained decoding | 0.62 | 0.63 | 0.66 |
| 4 parallel requests: rate of one request | 0.62 | 0.63 | 0.60 |

- The rate of the sustained decoding is the most stable value of the three windows: 0.62, 0.63
  and 0.66. The same holds for the rate of one request under 4 parallel requests: 0.62, 0.63 and
  0.60.
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

## Parallel requests

| Endpoint | One request | 4 parallel requests, total | Requests each second |
|---|---|---|---|
| CommandCode | 360.5 tokens/s | 866.2 tokens/s | 1.5 |
| OpenCode (Go) | 217.7 tokens/s | 429.5 tokens/s | 0.6 |

Four parallel requests do not lower the rate of one request on either route: the aggregate rate
is about twice the rate of one request on both sides, which is the same finding as in the two
windows before. The bottleneck of both routes holds at 4 parallel requests.

## Limits

- Each measurement has 1 to 20 samples, and the phases `models` and `concurrent` have 3 and 4
  samples for a side. A difference below 10 percent is noise. The comparison prints the number of
  samples of each side and names no winner for a phase of one sample.
- The absolute values of this campaign are not comparable with those of another window, because
  the host, the network path and the window differ. Compare the ratios only.
- The absolute values of a ratio of a delay are not comparable between rows either: the row of
  the reused socket is the least stable of the table, 9.11 to 20.58 over three windows. The rate
  of the sustained decoding is the most stable, 0.62 to 0.66.
- A rate needs a numerator. The tool prints no rate for a phase whose median answer holds fewer
  than 50 output tokens or fewer than 10 content tokens, so the `short` phase of this campaign
  holds no rate. Read a rate for long answers only.
- The number of model identifiers that a route lists is a count, not a score: CommandCode lists
  80 and OpenCode lists 35 in this window.
- The campaign did not test retries, tool calls, or streaming with tools.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_commandcode_20260923T210256Z.json` | 2026-09-23T21:02:56Z | This A/B test, CommandCode side, with 48 records in the `{meta, records}` format. |
| `ab_opencode-go_20260923T210256Z.json` | 2026-09-23T21:02:56Z | This A/B test, OpenCode (Go) side, with 48 records in the `{meta, records}` format. |

Both files carry the same time, because one command `bench.py ab` wrote the two sides together.
The other two windows of this host are in the directories `../2026-09-23T153444Z/` (the first) and
`../2026-09-23T204204Z/` (the second).
