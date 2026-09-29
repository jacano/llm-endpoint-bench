# Results: deepseek-flash on the vendor route (DeepSeek), Windows 11, 06:36Z

The run started at 2026-09-29T06:36:19Z (08:36 local time). Machine: Windows 11, host
`DESKTOP-08PBEHO`. Client: `curl` with a browser user agent. One route:

```
python bench.py run --endpoint deepseek-official
```

This route is not a gateway of a third party. It is the API of the vendor of the model itself,
`https://api.deepseek.com/v1` with `deepseek-flash`, which the two routes that the other rounds
measure, CommandCode and OpenCode (Go), resell under the id `deepseek-v4.1-flash`. The round exists
to read that route on this host, next to the two resold ones: a user of the vendor route pays no
gateway of a reseller, and this round measures what that is worth and what it costs.

- 21 clean records, no error: 3 `models`, 3 `models_reuse`, 1 `models_body`, 5 `short`, 4 `long`,
  4 `concurrent_4` and the concurrent summary.
- All four phases ran. The token counts come from the `usage` block of each response.
- The four `long` answers hold 500 visible tokens each, so a rate of that phase is a rate and not
  the edge of a short answer.
- The `models_body` record lists 2 model ids on the route and the model of the endpoint is one of
  them (`target_present`: true).
- The endpoint sends no `reasoning_effort`; the catalog of the route declares `high` as the default
  level, which is the level that the desktop agent of this host requests, so the two agree.

## The medians of this round

| Measurement | Median | Min | Max | n |
|---|---|---|---|---|
| DNS of `/models` | 6.1 ms | 4.7 ms | 39.4 ms | 3 |
| TCP connect, new connection | 14.6 ms | 13.5 ms | 48.7 ms | 3 |
| TLS handshake, new connection | 27.4 ms | 26.1 ms | 62.8 ms | 3 |
| TTFB of `/models`, new connection | 283.9 ms | 280.8 ms | 319.1 ms | 3 |
| TTFB of `/models`, reused connection | 252.9 ms | 250.0 ms | 285.6 ms | 3 |
| Short answer: TTFT of the first token | 779.1 ms | 624.4 ms | 919.7 ms | 5 |
| Short answer: TTFT of the visible token | 910.7 ms | 729.0 ms | 1117.6 ms | 5 |
| Short answer: total time | 913.9 ms | 732.4 ms | 1134.2 ms | 5 |
| Long answer: TTFT of the first token | 644.5 ms | 566.4 ms | 737.1 ms | 4 |
| Long answer: TTFT of the visible token | 1054.7 ms | 1027.0 ms | 1356.2 ms | 4 |
| Long answer: total time | 2212.3 ms | 2177.8 ms | 2481.3 ms | 4 |
| Long answer: TPS of the sustained decoding | 372.5 tokens/s | 347.7 | 397.6 | 4 |
| Long answer: TPS of the visible content | 439.1 tokens/s | 431.3 | 446.2 | 4 |
| 4 parallel requests: rate of one request | 320.5 tokens/s | 278.9 | 382.1 | 4 |
| 4 parallel requests: total rate | 788.7 tokens/s, 1.28 requests/s | - | - | 1 |

The `short` phase holds no rate: its median answer is 17 output tokens, of which 3 are visible, and
the tool prints no rate below 50 output tokens or 10 content tokens. The delay that a user feels on
that answer is the `TTFT of the first token`, 779.1 ms.

## Against the routes that resell the same model

The four rounds of 2026-09-23 and the two of 2026-09-29 measured CommandCode and OpenCode (Go) on
this host. CommandCode moved between those two days: its transport held and the model side of it
fell to about half its rate. The vendor route of this round sits at the model side of the first day
and at the transport of neither.

| Measurement | CommandCode, 09-23 (four rounds) | CommandCode, 09-29 (two rounds) | OpenCode (Go), 09-23 (four rounds) | This round |
|---|---|---|---|---|
| TLS handshake, new connection | 37.9 to 42.0 ms | 33.3 and 38.6 ms | 230.0 to 272.8 ms | 27.4 ms |
| TTFB of `/models`, reused connection | 15.8 to 32.0 ms | 14.0 and 14.6 ms | 250.7 to 325.2 ms | 252.9 ms |
| Short answer: TTFT of the first token | 753.8 to 844.0 ms | 1616.9 and 1638.7 ms | 1474.4 to 1822.3 ms | 779.1 ms |
| Long answer: TTFT of the visible token | 1204.1 to 1677.2 ms | 2758.0 and 3426.9 ms | 2043.5 to 2843.3 ms | 1054.7 ms |
| Long answer: total time | 2375.4 to 2839.3 ms | 5197.1 and 5611.7 ms | 4006.4 to 4645.6 ms | 2212.3 ms |
| Long answer: TPS of the sustained decoding | 362.9 to 378.0 tokens/s | 185.4 and 192.4 tokens/s | 234.1 to 260.3 tokens/s | 372.5 tokens/s |
| Long answer: TPS of the visible content | 438.9 to 446.3 tokens/s | 224.2 and 227.7 tokens/s | 260.4 to 291.9 tokens/s | 439.1 tokens/s |
| 4 parallel requests: rate of one request | 360.5 to 379.6 tokens/s | 199.8 and 201.6 tokens/s | 217.7 to 243.6 tokens/s | 320.5 tokens/s |
| 4 parallel requests: total rate | 808.6 to 901.8 tokens/s | 409.7 and 481.6 tokens/s | 423.9 to 577.3 tokens/s | 788.7 tokens/s |

- Every delay of the vendor route is the lowest of the four columns, and the short answer is where
  the margin is largest: 779.1 ms against 1616.9 and 1638.7 ms on CommandCode six minutes before
  this round, a quotient of 0.48. The same model, on the same host, at the same hour, answers a
  short prompt in half the time when no reseller sits between them.
- The five vendor rows of the model side of the second day of CommandCode land at 0.31 to 0.48 of
  its delays and at 1.59 to 2.01 of its rates, far outside the 10 percent noise of these
  measurements. Against the first day of CommandCode the margin is smaller and mixed: the short
  answer of this round sits inside the range of those four rounds, 779.1 ms against 753.8 to
  844.0 ms; the visible start of a long answer, 1054.7 ms, is below all four of them; the sustained
  rate, 372.5 tokens/s, and the rate of the visible content, 439.1 tokens/s, agree with them; the
  rate of one request under 4 parallel requests, 320.5 tokens/s, is below all four of them, 360.5
  to 379.6 tokens/s, and the aggregate rate, 788.7 tokens/s, sits just under their 808.6 to
  901.8 tokens/s.
- The transport rows separate the two halves of the vendor route. Its handshake is the cheapest
  measured on this host, 27.4 ms against 33.3 to 42.0 ms on CommandCode and 230.0 to 272.8 ms on
  OpenCode (Go); its per-request cost with a ready socket, 252.9 ms, is as expensive as the gateway
  of OpenCode (Go), 250.7 to 325.2 ms, and about seventeen times the 14.0 and 14.6 ms of
  CommandCode at 06:28Z and 06:29Z. So the gain of the vendor route is not a cheap edge: on a short
  answer the model of this round writes its first token 526 ms after that 252.9 ms of edge, where
  CommandCode on 09-23 wrote it 722 to 828 ms after an edge of 15.8 to 32.0 ms.
- 4 parallel requests cost this route more than they cost the resold ones. The rate of one request
  under load, 320.5 tokens/s, is 0.86 of the 372.5 tokens/s of one long answer alone, a fall of
  14 percent, where the worst fall of CommandCode across the four rounds of 09-23 was 6 percent.
  The aggregate stays at 2.46 times the rate of one request, 788.7 tokens/s, which is inside the
  range that the rounds of 09-23 hold, 808.6 to 901.8 tokens/s.
- The work of the answers does not explain these rows. This round wrote the same 500 visible tokens
  for the long prompt as every round before it, and 569 to 645 output tokens of which 69 to 145 were
  reasoning, inside the range of the rounds of 09-23.

## Limits

- One round, 1 to 5 samples for each phase, and one host. The `models` and `models_reuse` rows have
  3 samples and the concurrent summary has 1. A difference below 10 percent is noise.
- The comparison crosses the six days and the two days of the rounds it cites: a different hour and
  a different load of the provider. Read a quotient of two rounds as the state of the route at two
  moments, not as a property of the route.
- The round measures the vendor route through the OpenAI-compatible surface, `POST
  /v1/chat/completions`, which is the only surface that `bench.py` speaks.
- The round did not test retries, tool calls, or streaming with tools.
- The key of the route lives in `.env` beside the tool, which is in `.gitignore`; no result file and
  no summary holds it.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `deepseek-official_20260929T063619Z.json` | 2026-09-29T06:36:19Z | 21 records in the `{meta, records}` format, phases transport, short, long, concurrent. |

The rounds of the resold routes are in `../2026-09-23T153444Z/`, `../2026-09-23T204204Z/`,
`../2026-09-23T210256Z/`, `../2026-09-23T212350Z/`, `../2026-09-29T062827Z/` and
`../2026-09-29T062914Z/`; `../README.md` indexes all of them and `../../ANALYSIS.md` compares them.
