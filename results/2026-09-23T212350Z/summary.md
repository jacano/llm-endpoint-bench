# Results: deepseek-v4.1-flash on CommandCode and on OpenCode (Go), Windows 11, 21:23Z

The run started at 2026-09-23T21:23:50Z (23:23 local time). Machine: Windows 11. Client: `curl`
with a browser user agent. The two sides ran in the same session, in an interleaved A/B order.

Both routes serve the same model. CommandCode names it `deepseek/deepseek-v4.1-flash`. OpenCode
names it `deepseek-v4.1-flash`.

- CommandCode: 48 clean requests, no error.
- OpenCode (Go): 48 clean requests, no error.
- The phases `transport`, `short`, `long` and `concurrent` ran on both sides. Each phase has 3,
  20, 16 and 4 samples for a side, plus the concurrent summary.
- The tool reads each token count from the `usage` block of the response.

This is the fourth round on this host. It repeats the A/B test of the runs of 15:34:44Z,
20:42:04Z and 21:02:56Z on the same machine, twenty-one minutes after the third of them. The
phases are the four that the rounds before it hold, so the tables compare like with like. The
tool no longer writes the fields `platform` and `python` of the `meta` block, which no command
reads. The command was:

```
python bench.py ab --a commandcode --b opencode-go --n 4
```

## Comparison of the two routes

The table gives the median value of each measurement.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TLS handshake, new connection | 40.6 ms | 272.8 ms | 6.72 |
| TTFB of `/models`, new connection | 64.4 ms | 592.0 ms | 9.19 |
| TTFB of `/models`, reused connection | 27.1 ms | 296.8 ms | 10.95 |
| Short answer: TTFT of the first token | 753.8 ms | 1822.3 ms | 2.42 |
| Short answer: TTFT of the visible token | 819.3 ms | 1913.3 ms | 2.34 |
| Short answer: total time | 833.5 ms | 1912.3 ms | 2.29 |
| Long answer: TTFT of the first token | 796.6 ms | 1699.7 ms | 2.13 |
| Long answer: TTFT of the visible token | 1677.2 ms | 2043.5 ms | 1.22 |
| Long answer: total time | 2839.3 ms | 4006.4 ms | 1.41 |
| TPS of the sustained decoding | 362.9 tokens/s | 260.3 tokens/s | 0.72 |
| TPS of the visible content | 446.0 tokens/s | 291.9 tokens/s | 0.65 |
| 4 parallel requests: rate of one request | 366.7 tokens/s | 243.6 tokens/s | 0.66 |
| 4 parallel requests: total rate | 901.8 tokens/s and 1.5 requests/s | 423.9 tokens/s and 0.6 requests/s | 0.47 |

A ratio below 1 belongs to a rate, where a large number is better. CommandCode is faster on every
measurement.

## The ratios hold, the absolute values move

The same test has now run four times on this host. The direction of every difference is the same
in all four rounds, and the size of a difference moves with the queue of the provider.

| Measurement: OpenCode divided by CommandCode | 15:34 | 20:42 | 21:02 | 21:23 |
|---|---|---|---|---|
| TTFB of `/models`, reused connection | 11.77 | 9.11 | 20.58 | 10.95 |
| Short answer: TTFT of the first token | 1.75 | 2.20 | 2.16 | 2.42 |
| Long answer: TTFT of the visible token | 2.36 | 1.66 | 1.96 | 1.22 |
| Long answer: total time | 1.94 | 1.66 | 1.86 | 1.41 |
| TPS of the sustained decoding | 0.62 | 0.63 | 0.66 | 0.72 |
| TPS of the visible content | 0.63 | 0.59 | 0.61 | 0.65 |
| 4 parallel requests: rate of one request | 0.62 | 0.63 | 0.60 | 0.66 |

- The rate of the visible content is the most stable value of the four rounds: 0.63, 0.59, 0.61
  and 0.65. The rate of one request under 4 parallel requests is next: 0.62, 0.63, 0.60 and 0.66.
- The rate of the sustained decoding moved further than in the rounds before it, to 0.72, and the
  cause is in the two answers rather than in the routes: CommandCode wrote 684 output tokens for
  the long answer where OpenCode wrote 569, a difference of 20 percent, and the extra tokens are
  mostly reasoning (184 against 70). That rate divides the output tokens by the time of the
  generation, so the larger numerator lifts it. Both sides wrote 500 and 499 visible tokens, and
  the visible rate of the same answers is 0.65.
- The row of the reused socket is the least stable of the table, 9.11 to 20.58, and this round
  brought the two sides closer than the round before it: 27.1 ms on CommandCode against 296.8 ms
  on OpenCode. Read that row as the cost of the gateway at a moment, not as a property of the
  route.
- The ratios of the delays of the model itself stayed inside the range of the other rounds: the
  short answer at 2.42 against 1.75 to 2.20, the long answer at 1.22 against 1.66 to 2.36.

## Cause of the difference

The gateway of OpenCode adds a fixed cost to each request. With a ready socket, one request to
`/models` needs 296.8 ms on OpenCode and 27.1 ms on CommandCode. The handshake of a new TLS
connection adds 272.8 ms against 40.6 ms. The first byte of a model answer carries the same cost
before the model starts: the TTFT of the first token of a long answer is 1699.7 ms against
796.6 ms, a difference of 903 ms, while the delay from that token to the visible answer is
343.8 ms against 880.6 ms.

Sustained decoding is also slower on OpenCode in this round: the visible content arrives at
291.9 tokens/s against 446.0 tokens/s.

## Parallel requests

| Endpoint | One request | 4 parallel requests, total | Requests each second |
|---|---|---|---|
| CommandCode | 366.7 tokens/s | 901.8 tokens/s | 1.5 |
| OpenCode (Go) | 243.6 tokens/s | 423.9 tokens/s | 0.6 |

Four parallel requests do not lower the rate of one request on CommandCode: 366.7 tokens/s against
the 362.9 tokens/s of the sustained decoding of one request. On OpenCode the rate of one request
falls from 260.3 to 243.6 tokens/s, a difference of 6 percent. The aggregate rate is 2.5 times the
rate of one request on CommandCode and 1.7 times on OpenCode, so the bottleneck of both routes
still holds at 4 parallel requests.

## Limits

- Each measurement has 1 to 20 samples, and the phases `models` and `concurrent` have 3 and 4
  samples for a side. One `short` answer of OpenCode wrote no visible token at all, so the delay to
  its first visible token rests on 19 of the 20 answers, which the column `n` of a comparison
  shows. A difference below 10 percent is noise. The comparison names no winner for a phase of one
  sample.
- The absolute values of this round are not comparable with those of another round, because
  the host, the network path and the hour differ. Compare the ratios only.
- The two sides did not write the same number of output tokens in the `long` phase, 684 against
  569, so a timing or a rate of that phase measures the work of the answer as well as the route.
  The visible content of the two answers is the one part that matches, 500 tokens against 499.
- A rate needs a numerator. The tool prints no rate for a phase whose median answer holds fewer
  than 50 output tokens or fewer than 10 content tokens, so the `short` phase of this round
  holds no rate: its median answer is 17 output tokens, of which 3 are visible.
- The number of model identifiers that a route lists is a count, not a score: CommandCode lists
  80 and OpenCode lists 35 in this round.
- The round did not test retries, tool calls, or streaming with tools.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_commandcode_20260923T212350Z.json` | 2026-09-23T21:23:50Z | This A/B test, CommandCode side, with 48 records in the `{meta, records}` format. |
| `ab_opencode-go_20260923T212350Z.json` | 2026-09-23T21:23:50Z | This A/B test, OpenCode (Go) side, with 48 records in the `{meta, records}` format. |

Both files carry the same time, because one command `bench.py ab` wrote the two sides together.
The other three rounds of this host are in the directories `../2026-09-23T153444Z/` (the first),
`../2026-09-23T204204Z/` (the second) and `../2026-09-23T210256Z/` (the third).
