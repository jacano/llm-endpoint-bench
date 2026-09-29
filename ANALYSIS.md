# The analysis of the results

Ten rounds measured one model, `deepseek-v4.1-flash`, on one Windows 11 host, over three routes and
the five endpoints of `bench.py`: the API of the vendor of the model on each of its two surfaces,
and two gateways that resell it, CommandCode under two model ids and OpenCode (Go). Four rounds on
2026-09-23 measured the two resold routes against each other, between 15:34Z and 21:23Z. Six rounds
on 2026-09-29 measured one to three of the endpoints each, between 06:28Z and 11:58Z: the two resold
routes fell to about half their rate of six days before on the CommandCode side, the vendor route
was measured for the first time, it went against CommandCode, the two surfaces of it went against
each other, and the last round put the normal tier of CommandCode, its fast tier and the vendor in
one session.
This file holds their tables, what the differences come from, what holds between the rounds, and
the limits of the measurements.

| Route | Endpoint of `bench.py` | Surface | Base URL | Model id on the wire |
|---|---|---|---|---|
| The vendor of the model | `deepseek-official` | `openai-completions` | `https://api.deepseek.com/v1` | `deepseek-flash` |
| The vendor of the model | `deepseek-official-messages` | `anthropic-messages` | `https://api.deepseek.com/anthropic` | `deepseek-flash` |
| A reseller, CommandCode | `commandcode` | `openai-completions` | `https://api.commandcode.ai/provider/v1` | `deepseek/deepseek-v4.1-flash` |
| A reseller, CommandCode, the fast tier of the same service | `commandcode-fast` | `openai-completions` | `https://api.commandcode.ai/provider/v1` | `deepseek/deepseek-v4.1-flash-fast` |
| A reseller, OpenCode (Go) | `opencode-go` | `openai-completions` | `https://opencode.ai/zen/go/v1` | `deepseek-v4.1-flash` |

An endpoint of this tool is one surface of one service. The vendor of the model answers on both of
the surfaces that the tool speaks, so it holds two entries, and a comparison of the two of them is a
comparison of the paths of one service rather than of two providers.

The raw records and the full tables of each round are in `results/`, which `results/README.md`
indexes:

- `results/2026-09-23T153444Z/` — the first round: CommandCode against OpenCode (Go).
- `results/2026-09-23T204204Z/` — the second round, four hours later.
- `results/2026-09-23T210256Z/` — the third round, twenty minutes after the second one.
- `results/2026-09-23T212350Z/` — the fourth round, twenty-one minutes after the third one.
- `results/2026-09-29T062827Z/` — the fifth round, six days later, one route only (CommandCode).
- `results/2026-09-29T062914Z/` — the sixth round, 47 seconds after the fifth one, same route.
- `results/2026-09-29T063619Z/` — the seventh round, the vendor route alone on its OpenAI-compatible
  surface.
- `results/2026-09-29T064339Z/` — the eighth round, the vendor route against CommandCode, in an
  interleaved A/B.
- `results/2026-09-29T074529Z/` — the ninth round, the two surfaces of the vendor route against each
  other, in an interleaved A/B.
- `results/2026-09-29T115801Z/` — the tenth round, the normal tier of CommandCode, its fast tier and
  the vendor, in one interleaved session of three endpoints.

The tool that produced them is `bench.py`; the README states it.

## The first round (15:34Z)

CommandCode is faster than OpenCode (Go) on every measurement. The table gives the median value of
each measurement: TTFB is the delay before the response starts, and TTFT the delay before the
model writes the first token. The full tables are in `results/2026-09-23T153444Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | CommandCode is faster by |
|---|---|---|---|
| TLS handshake, new connection | 42.0 ms | 233.8 ms | 5.6 |
| TTFB of `/models`, new connection | 70.8 ms | 507.9 ms | 7.2 |
| TTFB of `/models`, reused connection | 21.3 ms | 250.7 ms | 11.8 |
| Short answer: TTFT of the first token | 844.0 ms | 1474.4 ms | 1.75 |
| Long answer: TTFT of the visible token | 1204.1 ms | 2843.3 ms | 2.36 |
| Long answer: total time | 2375.4 ms | 4604.1 ms | 1.94 |
| TPS of the sustained decoding | 378.0 tokens/s | 234.1 tokens/s | 1.61 |
| TPS of the visible content | 438.9 tokens/s | 276.1 tokens/s | 1.59 |
| 4 parallel requests: rate of one request | 379.6 tokens/s | 233.8 tokens/s | 1.61 |
| 4 parallel requests: total rate | 808.6 tokens/s | 577.3 tokens/s | 1.41 |

Every ratio is how many times faster CommandCode was, so a larger number is always a larger
gain for CommandCode, on a delay and on a rate alike.

## The second round (20:42Z)

The same A/B test ran again on the same host, four hours later. Every difference points the same
way; the size of a difference moves with the queue of the provider. The full tables are in
`results/2026-09-23T204204Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | CommandCode is faster by |
|---|---|---|---|
| TLS handshake, new connection | 38.6 ms | 247.9 ms | 6.42 |
| TTFB of `/models`, reused connection | 32.0 ms | 291.6 ms | 9.11 |
| Short answer: TTFT of the first token | 812.5 ms | 1784.8 ms | 2.20 |
| Long answer of 500 visible tokens: TTFT of the first visible token | 1462.2 ms | 2429.8 ms | 1.66 |
| Long answer of 500 visible tokens: total time | 2610.4 ms | 4337.5 ms | 1.66 |
| TPS of the sustained decoding | 372.1 tokens/s | 234.2 tokens/s | 1.59 |
| TPS of the visible content | 442.8 tokens/s | 260.4 tokens/s | 1.69 |
| 4 parallel requests: rate of one request | 377.6 tokens/s | 239.7 tokens/s | 1.59 |
| 4 parallel requests: total rate | 799.7 tokens/s | 478.8 tokens/s | 1.67 |

## The third round (21:02Z)

The same A/B test ran a third time on the same host, twenty minutes after the second round. Every
difference points the same way, and the delays of the model itself stayed inside the range of the
rounds before it. The full tables are in `results/2026-09-23T210256Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | CommandCode is faster by |
|---|---|---|---|
| TLS handshake, new connection | 37.9 ms | 230.0 ms | 6.07 |
| TTFB of `/models`, reused connection | 15.8 ms | 325.2 ms | 20.58 |
| Short answer: TTFT of the first token | 826.3 ms | 1781.7 ms | 2.16 |
| Long answer of 500 visible tokens: TTFT of the first visible token | 1380.4 ms | 2699.5 ms | 1.96 |
| Long answer of 500 visible tokens: total time | 2503.9 ms | 4645.6 ms | 1.86 |
| TPS of the sustained decoding | 373.1 tokens/s | 246.7 tokens/s | 1.52 |
| TPS of the visible content | 446.3 tokens/s | 273.4 tokens/s | 1.64 |
| 4 parallel requests: rate of one request | 360.5 tokens/s | 217.7 tokens/s | 1.67 |
| 4 parallel requests: total rate | 866.2 tokens/s | 429.5 tokens/s | 2.00 |

## The fourth round (21:23Z)

The same A/B test ran a fourth time on the same host, twenty-one minutes after the third round.
Every difference points the same way. The two answers of the `long` phase differed in length more
than in any round before, and the paragraph after the table states what that does to the rates of
that phase. The full tables are in `results/2026-09-23T212350Z/summary.md`.

| Measurement | CommandCode | OpenCode (Go) | CommandCode is faster by |
|---|---|---|---|
| TLS handshake, new connection | 40.6 ms | 272.8 ms | 6.72 |
| TTFB of `/models`, new connection | 64.4 ms | 592.0 ms | 9.19 |
| TTFB of `/models`, reused connection | 27.1 ms | 296.8 ms | 10.95 |
| Short answer: TTFT of the first token | 753.8 ms | 1822.3 ms | 2.42 |
| Long answer: TTFT of the visible token | 1677.2 ms | 2043.5 ms | 1.22 |
| Long answer: total time | 2839.3 ms | 4006.4 ms | 1.41 |
| TPS of the sustained decoding | 362.9 tokens/s | 260.3 tokens/s | 1.39 |
| TPS of the visible content | 446.0 tokens/s | 291.9 tokens/s | 1.54 |
| 4 parallel requests: rate of one request | 366.7 tokens/s | 243.6 tokens/s | 1.52 |
| 4 parallel requests: total rate | 901.8 tokens/s | 423.9 tokens/s | 2.13 |

The sustained decoding of a whole answer is where CommandCode gained least, 1.39 times, the lowest
of the four rounds, because
CommandCode wrote 684 output tokens for its long answer where OpenCode wrote 569: the numerator of
that rate grew by a fifth, and the extra tokens are mostly reasoning. The two answers held the
same visible content, 500 tokens against 499, and there CommandCode wrote 1.54 times faster.

## The rounds of 2026-09-29

### CommandCode on its own

Two rounds measured one route, CommandCode, six days after the four rounds of 09-23 and on the same
host. They ran `bench.py run --endpoint commandcode`, back to back, 47 seconds apart, so no second
route is in play and no ratio between routes exists in them. What they do show is which half of the
route moved. The full tables are in `results/2026-09-29T062827Z/summary.md` and
`results/2026-09-29T062914Z/summary.md`.

| Measurement of CommandCode | 09-23, four rounds | 09-29, two rounds | 09-29 divided by 09-23 |
|---|---|---|---|
| TLS handshake, new connection | 37.9 to 42.0 ms | 33.3 and 38.6 ms | 0.86 to 0.99 |
| TTFB of `/models`, reused connection | 15.8 to 32.0 ms | 14.0 and 14.6 ms | 0.72 to 0.96 |
| Short answer: TTFT of the first token | 753.8 to 844.0 ms | 1616.9 and 1638.7 ms | 2.01 to 2.03 |
| Long answer: TTFT of the visible token | 1204.1 to 1677.2 ms | 2758.0 and 3426.9 ms | 1.89 to 2.36 |
| Long answer: total time | 2375.4 to 2839.3 ms | 5197.1 and 5611.7 ms | 1.94 to 2.08 |
| Long answer: TPS of the sustained decoding | 362.9 to 378.0 tokens/s | 185.4 and 192.4 tokens/s | 0.50 to 0.52 |
| Long answer: TPS of the visible content | 438.9 to 446.3 tokens/s | 224.2 and 227.7 tokens/s | 0.50 to 0.51 |
| 4 parallel requests: rate of one request | 360.5 to 379.6 tokens/s | 199.8 and 201.6 tokens/s | 0.53 to 0.55 |
| 4 parallel requests: total rate | 808.6 to 901.8 tokens/s | 409.7 and 481.6 tokens/s | 0.48 to 0.56 |

- The transport of the route did not move. The handshake, the DNS, the TCP connect and the TTFB of
  `/models` with a ready socket sit at the fast end of the range that the four rounds of 09-23 hold,
  and the reused-socket TTFB, 14.0 and 14.6 ms, is the lowest value that this host has recorded.
- The model side of the same route is about twice as slow. Every delay of the model is 1.9 to 2.4
  times its value of 09-23, and every rate of the model is 0.50 to 0.55 of its value of 09-23.
- The two families are independent, and that is the finding. A gateway that charges 14 ms for a
  request cannot explain a short answer of 1.6 s where the same route answered in 0.8 s six days
  before, nor a decode of 190 tokens/s where it decoded at 370.
- The fall is not less work in the answer. The `long` answers of the two rounds hold 499 and 500
  visible tokens for the same prompt, the same as every round of 09-23, and 621.5 and 651 output
  tokens of which 122.5 and 152 were reasoning, inside the range of those rounds. The route
  decodes the same content at half the rate, and it takes twice as long to write the first token
  of it.
- Within the two rounds of 09-29 the stable rows are the ones a user feels on a short answer and
  under load: the short TTFT (1616.9 against 1638.7 ms), the sustained rate (192.4 against 185.4
  tokens/s) and the rate of one request under 4 parallel requests (199.8 against 201.6 tokens/s)
  agree within 2 to 4 percent. The delay to the first visible token of a long answer is the one row
  that does not, 2758.0 against 3426.9 ms, and the cause is visible in the record: the answer of
  the second round spent 152 reasoning tokens before it turned visible, against 122.5 in the first,
  with a worst sample of 277. The slow start of a long answer follows the reasoning that precedes
  it, not the route.
- 4 parallel requests still hold the rate of one request on this route: 199.8 and 201.6 tokens/s
  under load against 192.4 and 185.4 tokens/s for one request, and an aggregate of 2.1 and 2.6
  times the rate of one request.

The two rounds of 09-29 measured one hour of one day, six days after the rounds they are compared
against, and the load of a provider at that hour is not known. A difference of two times is far
outside the 10 percent noise of these measurements, so the direction is solid; the exact quotient
is not. Measure again before you change a route or a budget.

### The vendor route of the model

The seventh round measured the route of the vendor itself, and the eighth measured it against
CommandCode in one interleaved session, seven minutes later. The commands were:

```
python bench.py run --endpoint deepseek-official
python bench.py ab --a deepseek-official --b commandcode --n 4
```

The vendor route is the API of the vendor of the model, `https://api.deepseek.com/v1` with the id
`deepseek-flash`; the other two routes resell that same model under the ids
`deepseek/deepseek-v4.1-flash` and `deepseek-v4.1-flash`. The full tables are in
`results/2026-09-29T063619Z/summary.md` and `results/2026-09-29T064339Z/summary.md`.

| Measurement of the vendor route | 06:36Z, alone | 06:43Z, in the A/B |
|---|---|---|
| DNS of `/models` | 6.1 ms | 11.8 ms |
| TCP connect, new connection | 14.6 ms | 20.4 ms |
| TLS handshake, new connection | 27.4 ms | 33.0 ms |
| TTFB of `/models`, new connection | 283.9 ms | 282.8 ms |
| TTFB of `/models`, reused connection | 252.9 ms | 260.7 ms |
| Short answer: TTFT of the first token | 779.1 ms | 653.8 ms |
| Short answer: TTFT of the visible token | 910.7 ms | 784.4 ms |
| Short answer: total time | 913.9 ms | 790.7 ms |
| Long answer: TTFT of the first token | 644.5 ms | 692.8 ms |
| Long answer: TTFT of the visible token | 1054.7 ms | 1670.4 ms |
| Long answer: total time | 2212.3 ms | 2766.7 ms |
| Long answer: TPS of the sustained decoding | 372.5 tokens/s | 373.2 tokens/s |
| Long answer: TPS of the visible content | 439.1 tokens/s | 440.9 tokens/s |
| 4 parallel requests: rate of one request | 320.5 tokens/s | 386.0 tokens/s |
| 4 parallel requests: total rate | 788.7 tokens/s | 1067.7 tokens/s |

The A/B of 06:43Z is the comparison that this file could not make before it: the route of the vendor
of the model against a route that resells it, in one session, so the load of the provider hit both
the same way.

| Measurement | CommandCode | Vendor route | CommandCode divided by the vendor route |
|---|---|---|---|
| DNS of `/models` | 8.2 ms | 11.8 ms | 0.69 |
| TCP connect, new connection | 17.9 ms | 20.4 ms | 0.88 |
| TLS handshake, new connection | 36.1 ms | 33.0 ms | 1.09 (same) |
| TTFB of `/models`, new connection | 54.3 ms | 282.8 ms | 5.21 |
| TTFB of `/models`, reused connection | 18.5 ms | 260.7 ms | 14.09 |
| Short answer: TTFT of the first token | 1651.6 ms | 653.8 ms | 2.53 |
| Short answer: TTFT of the visible token | 1795.9 ms | 784.4 ms | 2.29 |
| Short answer: total time | 1802.7 ms | 790.7 ms | 2.28 |
| Long answer: TTFT of the first token | 1820.8 ms | 692.8 ms | 2.63 |
| Long answer: TTFT of the visible token | 3497.6 ms | 1670.4 ms | 2.09 |
| Long answer: total time | 5652.9 ms | 2766.7 ms | 2.04 |
| Long answer: TPS of the sustained decoding | 201.0 tokens/s | 373.2 tokens/s | 0.54 |
| Long answer: TPS of the visible content | 238.8 tokens/s | 440.9 tokens/s | 0.54 |
| 4 parallel requests: rate of one request | 199.8 tokens/s | 386.0 tokens/s | 0.52 |
| 4 parallel requests: total rate | 356.7 tokens/s | 1067.7 tokens/s | 0.33 |

- The two families of measurement split, and they split in opposite directions. CommandCode wins
  every row of the transport, and by 14.09 times on a ready socket. The vendor route wins every row
  of the model: 2.04 to 2.63 times on the delays and 1.85 times on the rates. A route is therefore
  not faster or slower than the other; it is cheaper before the model runs and dearer inside it.
- The gain of the vendor route is not a cheap edge, and the edge is not the handshake. Its TLS
  handshake, 27.4 ms in the round of 06:36, is the cheapest that this host has recorded, and the two
  rows that resolve the name and open the socket are 8.2 against 11.8 ms and 17.9 against 20.4 ms,
  too small to hold the wait that follows them. What the vendor route pays is the wait after the
  connection is ready: 252.9 to 260.7 ms before the model is asked anything, against 14.0 to
  18.5 ms on CommandCode. On a short answer the model of the vendor route writes its first token
  393 ms after that wait, where the model behind CommandCode writes it 1633 ms after its own.
- That is why the vendor route wins the row a user feels even while it loses the transport: the
  short answer is written in 653.8 ms against 1651.6 ms, and the wait of 260.7 ms is inside the
  second that separates them. What a user pays for the cheaper edge of CommandCode is a model that
  starts a second later and decodes at 201.0 tokens/s against 373.2.
- The rate of the visible content is the row to trust for the rates of that A/B, because the two
  sides did not write the same work: in `concurrent_4` the vendor route wrote 1122 output tokens of
  which 622 were reasoning, against 635.5 and 136.5 on CommandCode, and the aggregate rate of
  2.99 times therefore measures the answers as well as the routes. The visible content is the same
  500 tokens on both sides, and its rate, 1.87 times, carries no such caveat.
- 4 parallel requests do not cost the vendor route its rate in this round: 386.0 tokens/s for one
  request under load against 373.2 tokens/s for one long answer alone. The round of 06:36, seven
  minutes before, held a fall of 14 percent on that row. Read the two together as a range of the
  queue of the provider, not as a property of the route.
- The rates of the vendor route are stable across the seven minutes between its two rounds, 372.5
  then 373.2 tokens/s and 439.1 then 440.9, and its short answer is not: 779.1 ms then 653.8 ms, a
  move of 16 percent. CommandCode held its own short answer across the same morning, 1616.9, 1638.7
  and 1651.6 ms, and its rate, 185.4 to 201.0 tokens/s.

### The three routes on the morning of 2026-09-29

| Measurement | CommandCode 06:28Z | CommandCode 06:29Z | Vendor 06:36Z | CommandCode 06:43Z | Vendor 06:43Z |
|---|---|---|---|---|---|
| TTFB of `/models`, reused connection | 14.6 ms | 14.0 ms | 252.9 ms | 18.5 ms | 260.7 ms |
| Short answer: TTFT of the first token | 1616.9 ms | 1638.7 ms | 779.1 ms | 1651.6 ms | 653.8 ms |
| Long answer: TTFT of the visible token | 2758.0 ms | 3426.9 ms | 1054.7 ms | 3497.6 ms | 1670.4 ms |
| Long answer: total time | 5197.1 ms | 5611.7 ms | 2212.3 ms | 5652.9 ms | 2766.7 ms |
| Long answer: TPS of the sustained decoding | 192.4 tokens/s | 185.4 tokens/s | 372.5 tokens/s | 201.0 tokens/s | 373.2 tokens/s |
| Long answer: TPS of the visible content | 224.2 tokens/s | 227.7 tokens/s | 439.1 tokens/s | 238.8 tokens/s | 440.9 tokens/s |
| 4 parallel requests: rate of one request | 199.8 tokens/s | 201.6 tokens/s | 320.5 tokens/s | 199.8 tokens/s | 386.0 tokens/s |

- The transport rows of the two routes repeat across the morning, 14.0 to 18.5 ms against 252.9 to
  260.7 ms, a quotient of 13.7 to 18.6 between them: that difference is a property of the two routes
  on this host, not of the hour.
- The rates of the model repeat as well: 185.4 to 201.0 tokens/s on CommandCode against 372.5 to
  373.2 on the vendor route, and 224.2 to 238.8 against 439.1 to 440.9 on the visible content.
- The delay to the first visible token of a long answer is the row that moves most on both sides,
  2758.0 to 3497.6 ms on CommandCode and 1054.7 to 1670.4 ms on the vendor route, and the cause is
  in the records: it follows the reasoning that precedes the visible text, which ran from 36 to 722
  tokens across the answers of the A/B.

### The two surfaces of the vendor route

The ninth round put the two surfaces of one service against each other, interleaved, ten minutes
after the eighth:
`python bench.py ab --a deepseek-official --b deepseek-official-messages --n 4`. Both sides carry
the same model id, `deepseek-flash`, and the same key, so the round measures two paths of one
service and nothing else. Its tables are in `results/2026-09-29T074529Z/summary.md`.

| Measurement | OpenAI-compatible | Messages | Messages divided by OpenAI-compatible |
|---|---|---|---|
| TTFB of the probe, new connection | 300.4 ms | 378.6 ms | 1.26 |
| Total time of the probe, new connection | 300.5 ms | 693.4 ms | 2.31 |
| TTFB of the probe, reused connection | 312.7 ms | 289.7 ms | 0.93 (same) |
| Short answer: TTFT of the first token | 673.6 ms | 695.4 ms | 1.03 (same) |
| Short answer: TTFT of the visible token | 825.5 ms | 820.2 ms | 0.99 (same) |
| Short answer: total time | 828.9 ms | 822.9 ms | 0.99 (same) |
| Long answer: TTFT of the first token | 674.3 ms | 719.3 ms | 1.07 (same) |
| Long answer: TTFT of the visible token | 1344.1 ms | 1284.4 ms | 0.96 (same) |
| Long answer: total time | 2524.4 ms | 2422.6 ms | 0.96 (same) |
| Long answer: TPS of the sustained decoding | 367.2 tokens/s | 356.5 tokens/s | 0.97 (same) |
| 4 parallel requests: rate of one request | 359.0 tokens/s | 361.8 tokens/s | 1.01 (same) |
| 4 parallel requests: total rate | 780.9 tokens/s | 672.9 tokens/s | 0.86 |

- Every row of a phase of the model comes out `same` at the 10 percent threshold of the tool, from
  the short answer, 673.6 against 695.4 ms, to the rate of one request under load, 359.0 against
  361.8 tokens/s. The surface that a client speaks does not change the latency of the model behind
  it, and the round is what turns that from a guess into a measurement.
- The two rows of the transport that look like a difference are not one. The probe of the
  OpenAI-compatible surface is `GET /models`, a body of no tokens; the probe of the Messages one is
  the smallest message that surface takes, one token, streamed. Its TTFB is comparable within a
  quarter, 300.4 against 378.6 ms on a new connection and 312.7 against 289.7 ms with a ready
  socket, and its total time is not comparable at all, 300.5 against 693.4 ms, because the second
  probe waits for the model to write its token. Each transport record of that round names its probe.
- What a surface changes is what a client can learn, not what the service costs. The Messages
  surface reports no reasoning split, so `reasoning_tokens`, `content_tokens` and
  `tok_per_s_visible` have no value on its side of the table: the round of the two surfaces is the
  first of this file whose comparison cannot fill three of its rows. The sustained rate of the whole
  answer is the rate that both sides hold, and there the two agree, 367.2 against 356.5 tokens/s.
- The work of the two sides is close and not identical: the `long` phase wrote 611 output tokens on
  the OpenAI-compatible side and 642 on the Messages one, inside the fifth that the tool tolerates
  before it warns, so a rate of that phase is a rate of the path and not of a longer answer.


### The fast tier of the reseller, and the three of them in one session

The tenth round put three endpoints in one interleaved session:
`python bench.py ab --a commandcode --b deepseek-official --c commandcode-fast --n 4`. The two
CommandCode sides are two model ids of one service on one base URL, `deepseek/deepseek-v4.1-flash`
and `deepseek/deepseek-v4.1-flash-fast`; the third side is the API of the vendor of the model. Each
cell below is the second endpoint of the pair divided by the first, as `compare` prints it: on a
delay, below 1 means that the second is the faster one, and on a rate it means that the first is.
The full tables are in `results/2026-09-29T115801Z/summary.md`.

| Measurement | fast ÷ `commandcode` | vendor ÷ fast | vendor ÷ `commandcode` |
|---|---|---|---|
| TTFB of `/models`, reused connection | 0.97 (same) | 15.93 | 15.45 |
| Short answer: TTFT of the first token | 0.53 | 0.76 | 0.40 |
| Long answer: TTFT of the visible token | 0.36 | 1.18 | 0.43 |
| Long answer: total time | 0.44 | 1.06 (same) | 0.47 |
| Long answer: TPS of the visible content | 1.80 | 0.99 (same) | 1.79 |
| 4 parallel requests: rate of one request | 1.75 | 1.02 (same) | 1.79 |
| 4 parallel requests: total rate | 1.81 | 1.15 | 2.08 |

- The fast tier of the reseller is faster than its normal tier by 1.70 to 1.81 times on the rates and
  by 1.67 to 2.78 times on the delays of the model, on one base URL, one key and one edge: 939.4 ms
  of short answer against 1777.3, 1343.7 ms to the first visible token of a long answer against
  3718.2, and 370.1 tokens/s of sustained decoding against 217.8. A model id on a reseller is not a
  model any more than a route is: the two ids of this one are two different services to a user of it.
- The fast tier and the vendor of the model are one measurement apart on every rate — 370.1 against
  367.6 tokens/s sustained, 446.6 against 442.7 on the visible content, 361.4 against 368.2 for one
  request under load, all `same` — and on the total time of a long answer, 2500.4 against 2648.4 ms.
  The vendor keeps the short answer, 715.0 against 939.4 ms, and the fast tier keeps the start of a
  long answer, 1343.7 against 1581.3 ms.
- The split of the two halves of a route is in the same table, and the fast tier is the endpoint that
  holds both: the edge of the reseller, 15.9 and 16.4 ms on a ready socket against the 253.3 of the
  vendor, and a decode at the rate of the vendor, 370.1 against 367.6 tokens/s.
- The normal tier of the reseller is the slow side of this round on every row of the model, and its
  work is the cause of the rate rows. Its `long` answers wrote 896 output tokens of which 397 were
  reasoning, against 590 and 90 for the fast tier and 635 and 135 for the vendor, and several of them
  stopped at the 1200-token cap of that phase. Its visible content is the same 499 and 500 tokens as
  the other two, and the rate of that content, 247.9 against 446.6 and 442.7 tokens/s, is the row
  that compares the three without that caveat.

### OpenCode (Go) could not be measured on 2026-09-29

A third A/B of that morning, `python bench.py ab --a commandcode --b opencode-go --n 4`, was started
and stopped: every completion of the OpenCode (Go) side came back `403` with the body
`An active OpenCode Go subscription is required to use Go models`. The key of that route on that
machine resolves, and its `/models` answers `200` with 30 model ids, of which `deepseek-v4.1-flash`
is one, so a round of it would carry a transport table and no model at all. No round file was
written for it, and every comparison of OpenCode (Go) in this file is therefore the one of
2026-09-23, six days before these rounds.

That round is also the one that found two defects of the runner. A refused stream was recorded as a
clean row of nulls, because the tool read only the lines that start with `data:` and the body of a
refusal is one JSON object; and the three requests of the reused-socket probe were read out of every
number in the output, where `-o` pairs with the URL that follows it, so the bodies of the second and
the third transfer were left on stdout for the reader of the timings. `bench.py` now asks `curl` for
the status of each streaming request, records a stream that carries no delta as an error with the
status and a sample of the body beside it, and reads the timings of the reused probe from a marked
token of its own. A route that answers and does not serve states itself in the records instead of
entering the medians as a row of nulls.

The keys of the rounds are read from the environment of the process or from the `.env` file beside
the tool, on every platform; no result file and no summary holds one.


## What holds between the rounds

The four rounds of 2026-09-23 hold the table of the two resold routes against each other.

The direction of every difference is the same in all four rounds. The size of a difference moves
with the queue of the provider, and two families of measurement move differently.

| CommandCode is faster by | 15:34 | 20:42 | 21:02 | 21:23 |
|---|---|---|---|---|
| TTFB of `/models`, reused connection | 11.77 | 9.11 | 20.58 | 10.95 |
| Short answer: TTFT of the first token | 1.75 | 2.20 | 2.16 | 2.42 |
| Long answer: TTFT of the visible token | 2.36 | 1.66 | 1.96 | 1.22 |
| Long answer: total time | 1.94 | 1.66 | 1.86 | 1.41 |
| TPS of the sustained decoding | 1.61 | 1.59 | 1.52 | 1.39 |
| TPS of the visible content | 1.59 | 1.69 | 1.64 | 1.54 |
| 4 parallel requests: rate of one request | 1.61 | 1.59 | 1.67 | 1.52 |

- The rates are the stable family, and the visible content of a long answer is the most stable of
  them: 1.59, 1.69, 1.64 and 1.54. One request under 4 parallel requests gives 1.61, 1.59, 1.67 and
  1.52.
- The sustained decoding of a whole answer moved further than the others, from 1.61 to 1.39, and the
  fourth round shows the cause. That measurement divides the output tokens of an answer by
  the time of its generation, and the two `long` answers differed by a fifth in output tokens: 684
  on CommandCode against 569 on OpenCode, because CommandCode spent more of them on reasoning, 184
  against 70. The larger numerator lifts that rate. The visible content of the same two answers
  matched, 500 tokens against 499, and there the gain moved least of all.
- The ratios of the delays moved further in the fourth round than in the others: the gap in the
  TTFT of a short answer went from 1.75 to 2.42 across the four rounds, and the gap in the long
  answer fell from 2.36 to 1.22, where the two routes came closest. Both sides moved in that
  round, and a fixed cost of the gateway plus a varying queue explains both.
- The row of the reused socket is the least stable of the table, 9.11 to 20.58, and the fourth
  round landed near the low end of that range, 10.95. Read a row of this kind as the cost of the
  gateway at a moment, not as a property of the route.
- The gateway overhead of OpenCode is stable in absolute terms: 250.7 ms, 291.6 ms, 325.2 ms and
  296.8 ms with a ready socket, against 21.3 ms, 32.0 ms, 15.8 ms and 27.1 ms on CommandCode.
- 4 parallel requests do not lower the rate of one request on either route in any of the four
  rounds. The worst case is OpenCode in the fourth round, 243.6 tokens/s against the 260.3 of one
  request, a fall of 6 percent. The aggregate rate stays between 1.7 and 2.5 times the rate of one
  request, so the bottleneck of both routes holds at 4 parallel requests.
- The model always reasons before it answers, in every round: the prompt `Reply with exactly:
  pong` spends 14 reasoning tokens for a visible answer of 3 tokens in the fourth round, and about
  the same in the rounds before it.

## Limits

Each round ran for about 10 minutes on one machine. Each measurement has 1 to 20 samples, and
the table of a comparison prints the number of samples of each side, so a phase of one sample shows
a ratio without a verdict. A difference below 10 percent is noise. The queue of the provider
changes between rounds: the TTFT of one endpoint went from 620 ms to 2660 ms for the same prompt.
The absolute values of two rounds are not comparable, because the host, the network path and the hour differ; compare the ratios only. The round did not test retries, tool calls, or streaming
with tools. A measurement becomes stale, so measure again before you change a route or a budget.

- The six rounds of 2026-09-29 measure the five endpoints inside five and a half hours of one day, so
  a ratio of one of them holds two routes, two model ids or two surfaces at one moment, not a
  property of either.
- The rounds of that morning compare routes that do not write the same number of output tokens for
  the same prompt. In the A/B of 06:43Z the `long` phase differs by 8 percent (698 against 646.5
  output tokens) and the `concurrent_4` phase by 77 percent (635.5 against 1122, of which 136.5
  against 622 are reasoning); in the A/B of 07:45Z the `long` phase differs by 5 percent (611
  against 642). The tool prints that under its table; the rate of the visible content is the row
  that survives it, because it divides the same visible answer by the time on both sides — and on a
  comparison against the Messages surface that row exists on one side only, which the tool also
  prints.
- The vendor route is measured on both of its surfaces, and the two of them are not
  interchangeable: a table of the OpenAI-compatible one holds rows (`reasoning_tokens`,
  `content_tokens`, `tok_per_s_visible`) that the Messages one cannot fill, because the usage
  events of that surface report no reasoning split of the output tokens. The transport rows differ
  in the probe: `GET /models`, a body of no tokens, against one streamed message of one token whose
  TTFB holds the first event of the model as well as the edge.
- OpenCode (Go) holds no round of 2026-09-29: its subscription refused every completion of that day
  while the transport of the route went on answering. Its rows in this file come from 2026-09-23.

The `summary.md` of each round states the limits of that round, including the phases of it
that hold too few tokens for a rate.
