# Results: DeepSeek V4.1 Flash on the vendor route and on CommandCode, Windows 11, 06:43Z

The run started at 2026-09-29T06:43:39Z (08:43 local time). Machine: Windows 11, host
`DESKTOP-08PBEHO`. Client: `curl` with a browser user agent. The two sides ran in the same session,
in an interleaved A/B order, so the load of the provider hit both of them the same way.

Both routes serve the same model. The vendor route names it `deepseek-flash`; CommandCode names it
`deepseek/deepseek-v4.1-flash` and resells it. The command was:

```
python bench.py ab --a deepseek-official --b commandcode --n 4
```

- The vendor route: 48 clean requests, no error.
- CommandCode: 48 clean requests, no error.
- The phases `transport`, `short`, `long` and `concurrent` ran on both sides. Each phase has 3, 20,
  16 and 4 samples for a side, plus the concurrent summary.
- The tool reads each token count from the `usage` block of the response.
- The delay to the first visible token of the `short` phase holds 20 samples on CommandCode and 19
  on the vendor route: one short answer of the vendor route spent all 64 tokens of its budget on
  reasoning and never wrote a visible one.

## Comparison of the two routes

The table gives the median value of each measurement. A value below 1 in the last column belongs to
a rate, where a large number is better.

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
| TPS of the sustained decoding | 201.0 tokens/s | 373.2 tokens/s | 0.54 |
| TPS of the visible content | 238.8 tokens/s | 440.9 tokens/s | 0.54 |
| 4 parallel requests: rate of one request | 199.8 tokens/s | 386.0 tokens/s | 0.52 |
| 4 parallel requests: total rate | 356.7 tokens/s and 0.5 requests/s | 1067.7 tokens/s and 1.1 requests/s | 0.33 |

The tool names the vendor route faster on every measurement of the model, and CommandCode faster on
every measurement of the transport except the TLS handshake, which it calls `same`. The two families
do not agree, and the split is the finding of this round.

## The split between the transport and the model

- CommandCode reaches the edge of its gateway in 54.3 ms for a `/models` request on a new
  connection and in 18.5 ms with a ready socket; the vendor route takes 282.8 ms and 260.7 ms. The
  handshake is not the cause: the TLS handshake of the vendor route, 33.0 ms, is the cheaper of the
  two, and the tool calls that row `same`. Neither is the way to the edge: the name resolves in 8.2
  against 11.8 ms and the socket connects in 17.9 against 20.4 ms, and there CommandCode is the
  faster of the two by 1.44 and 1.14 times, delays too small to explain the wait that follows. What
  the vendor route pays is the wait after the connection is ready, 260.7 ms before the model is
  asked anything.
- The model of the vendor route then costs less than the model behind CommandCode, and by more than
  that 260 ms: on a short prompt its first token is written 653.8 ms in, which is 393 ms after its
  own edge, against 1651.6 ms on CommandCode, which is 1633 ms after its own.
- The rates agree on the same story and are the most stable rows of the table: the sustained
  decoding of a long answer runs at 373.2 tokens/s on the vendor route against 201.0 on
  CommandCode, 1.86 times, and the visible content at 440.9 against 238.8, 1.85 times. The
  4 parallel phase holds both rates: 386.0 against 199.8 tokens/s for one request, and 1067.7
  against 356.7 tokens/s in aggregate.
- 4 parallel requests do not cost the vendor route its rate in this round. Its rate of one request
  under load, 386.0 tokens/s, is above the 373.2 tokens/s of one long answer alone, and the 14
  percent fall that the round of `../2026-09-29T063619Z/` held is not repeated here. That row moves
  with the queue of the provider: read the two rounds together as a range, not as a property of the
  route.
- A count is not a score, and two of them move in opposite directions in this round. The vendor
  route lists 2 model ids where CommandCode lists 84. In the `long` phase both sides wrote the same
  500 visible tokens, and CommandCode spent more of its output on reasoning, 199 against 146.5. In
  the `concurrent_4` phase the relation is inverted and large: the vendor route wrote 1122 output
  tokens of which 622 were reasoning, against 635.5 and 136.5 on CommandCode. The aggregate rate of
  that phase, 2.99 times, therefore measures the work of the answers as well as the route: the same
  four prompts drew 4062 output tokens from one side and 2649 from the other. The rate of the
  visible content, 1.87 times, divides the same 500 tokens by the time and carries no such caveat.

## Against the rounds of the same morning

The vendor route was measured alone 7 minutes before this A/B
(`../2026-09-29T063619Z/`), and CommandCode ran twice 14 minutes before it
(`../2026-09-29T062827Z/` and `../2026-09-29T062914Z/`). The four rounds are one morning of one host.

| Measurement | CommandCode 06:28Z | CommandCode 06:29Z | Vendor route 06:36Z | CommandCode 06:43Z | Vendor route 06:43Z |
|---|---|---|---|---|---|
| TTFB of `/models`, reused connection | 14.6 ms | 14.0 ms | 252.9 ms | 18.5 ms | 260.7 ms |
| Short answer: TTFT of the first token | 1616.9 ms | 1638.7 ms | 779.1 ms | 1651.6 ms | 653.8 ms |
| Long answer: TTFT of the visible token | 2758.0 ms | 3426.9 ms | 1054.7 ms | 3497.6 ms | 1670.4 ms |
| Long answer: total time | 5197.1 ms | 5611.7 ms | 2212.3 ms | 5652.9 ms | 2766.7 ms |
| Long answer: TPS of the sustained decoding | 192.4 tokens/s | 185.4 tokens/s | 372.5 tokens/s | 201.0 tokens/s | 373.2 tokens/s |
| Long answer: TPS of the visible content | 224.2 tokens/s | 227.7 tokens/s | 439.1 tokens/s | 238.8 tokens/s | 440.9 tokens/s |
| 4 parallel requests: rate of one request | 199.8 tokens/s | 201.6 tokens/s | 320.5 tokens/s | 199.8 tokens/s | 386.0 tokens/s |

- The transport rows repeat in both rounds of each route, 14.0 to 18.5 ms against 252.9 to 260.7 ms,
  a quotient of 13.7 to 18.6 between them. The difference is a property of the two routes on this
  host, not of the hour.
- The rates of the model repeat as well: 185.4 to 201.0 tokens/s on CommandCode against 372.5 to
  373.2 on the vendor route, and 224.2 to 238.8 against 439.1 to 440.9 for the visible content.
- The delays of the model moved between the rounds, and the vendor route moved more than CommandCode
  did: its short answer went from 779.1 to 653.8 ms in 7 minutes, 16 percent, where CommandCode held
  1616.9, 1638.7 and 1651.6 ms across 15 minutes. The delay to the first visible token of a long
  answer is the row that moves most on both sides, 2758.0 to 3497.6 ms on CommandCode and 1054.7 to
  1670.4 ms on the vendor route, and the cause is visible in the records: it follows the reasoning
  that precedes the visible text, which ran from 36 to 722 tokens across the answers of this A/B.

## Limits

- One round, in an interleaved A/B order. 3 to 20 samples for each phase and each side, one host.
  The `models` and `models_reuse` rows have 3 samples and each concurrent summary has 1, so the tool
  prints no verdict for the phases of one sample and calls the TLS row `same`. A difference below
  10 percent is noise.
- The two sides do not write the same number of output tokens in `long` (698 against 646.5) nor in
  `concurrent_4` (635.5 against 1122); the same 500 visible tokens are the only part of the work
  that matches, and the tool says so under its table. Read a rate of those phases with that in hand.
- The comparison crosses no day: every round of it started on 2026-09-29 between 06:28Z and 06:43Z on
  this host. It still measures the state of two routes at two moments, not a property of them.
- The two sides are read through the OpenAI-compatible surface, `POST /v1/chat/completions`, which is
  the only surface that `bench.py` speaks.
- The round did not test retries, tool calls, or streaming with tools.
- The keys of the two routes are read from the environment of the process or from `.env` beside the
  tool, which is in `.gitignore`; no result file and no summary holds one.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_commandcode_20260929T064339Z.json` | 2026-09-29T06:43:39Z | The A/B test, CommandCode side, with 48 records and the phases transport, short, long and concurrent. |
| `ab_deepseek-official_20260929T064339Z.json` | 2026-09-29T06:43:39Z | The A/B test, vendor route side, with 48 records and the same phases. |

The round of the vendor route alone is in `../2026-09-29T063619Z/`, and the two rounds of CommandCode
of this morning are in `../2026-09-29T062827Z/` and `../2026-09-29T062914Z/`; `../README.md` indexes
all of them and `../../ANALYSIS.md` holds the comparison of all the rounds.
