# Results: deepseek-v4.1-flash on CommandCode, Windows 11, 06:28Z

The run started at 2026-09-29T06:28:27Z (08:28 local time). Machine: Windows 11, host
`DESKTOP-08PBEHO`. Client: `curl` with a browser user agent. One route only:

```
python bench.py run --endpoint commandcode
```

OpenCode (Go) is not measured in this round: this is a latency reading of the route that the
desktop agent of this machine runs on, `command-code` with `deepseek/deepseek-v4.1-flash`, and the
second route of the A/B is not in play.

- 21 clean records, no error: 3 `models`, 3 `models_reuse`, 1 `models_body`, 5 `short`, 4 `long`,
  4 `concurrent_4` and the concurrent summary.
- All four phases ran. The token counts come from the `usage` block of each response.
- The two answers of the `long` phase hold 499 and 500 visible tokens, so a rate of that phase is a
  rate and not the edge of a short answer.

## The medians of this round

| Measurement | Median | Min | Max | n |
|---|---|---|---|---|
| DNS of `/models` | 7.7 ms | 6.4 ms | 26.8 ms | 3 |
| TCP connect, new connection | 19.0 ms | 15.0 ms | 36.7 ms | 3 |
| TLS handshake, new connection | 38.6 ms | 30.7 ms | 59.7 ms | 3 |
| TTFB of `/models`, new connection | 55.6 ms | 46.0 ms | 74.6 ms | 3 |
| TTFB of `/models`, reused connection | 14.6 ms | 13.9 ms | 61.2 ms | 3 |
| Short answer: TTFT of the first token | 1616.9 ms | 1464.8 ms | 1989.7 ms | 5 |
| Short answer: TTFT of the visible token | 1746.9 ms | 1630.6 ms | 2067.9 ms | 5 |
| Short answer: total time | 1785.5 ms | 1661.6 ms | 2076.2 ms | 5 |
| Long answer: TTFT of the first token | 1914.5 ms | 1498.5 ms | 2731.1 ms | 4 |
| Long answer: TTFT of the visible token | 2758.0 ms | 2480.9 ms | 3754.4 ms | 4 |
| Long answer: total time | 5197.1 ms | 4579.7 ms | 5953.3 ms | 4 |
| Long answer: TPS of the sustained decoding | 192.4 tokens/s | 177.2 | 212.7 | 4 |
| Long answer: TPS of the visible content | 224.2 tokens/s | 192.5 | 242.3 | 4 |
| 4 parallel requests: rate of one request | 199.8 tokens/s | 190.3 | 211.5 | 4 |
| 4 parallel requests: total rate | 409.7 tokens/s, 0.48 requests/s | - | - | 1 |

The `short` phase holds no rate: its median answer is 17 output tokens, of which 3 are visible, and
the tool prints no rate below 50 output tokens or 10 content tokens.

## Against the CommandCode sides of 2026-09-23

The four rounds of 2026-09-23 measured this same route on this same host. The transport of the
gateway is unchanged, and the model side of the route is about twice as slow.

| Measurement | 2026-09-23 (four rounds) | This round | This round divided by 09-23 |
|---|---|---|---|
| TLS handshake, new connection | 37.9 to 42.0 ms | 38.6 ms | 0.99 |
| TTFB of `/models`, reused connection | 15.8 to 32.0 ms | 14.6 ms | 0.72 |
| Short answer: TTFT of the first token | 753.8 to 844.0 ms | 1616.9 ms | 2.03 |
| Long answer: TTFT of the visible token | 1204.1 to 1677.2 ms | 2758.0 ms | 1.89 |
| Long answer: total time | 2375.4 to 2839.3 ms | 5197.1 ms | 1.94 |
| Long answer: TPS of the sustained decoding | 362.9 to 378.0 tokens/s | 192.4 tokens/s | 0.52 |
| Long answer: TPS of the visible content | 438.9 to 446.3 tokens/s | 224.2 tokens/s | 0.50 |
| 4 parallel requests: rate of one request | 360.5 to 379.6 tokens/s | 199.8 tokens/s | 0.54 |
| 4 parallel requests: total rate | 808.6 to 901.8 tokens/s | 409.7 tokens/s | 0.48 |

The quotients of the delays are above 1 and the quotients of the rates are below 1, so every
model-side measurement of this round is about 1.9 to 2.0 times worse than the rounds of six days
before it. The gateway rows moved the other way, to the fast end of their range: the handshake and
the reused-socket TTFB are as cheap as they have ever been.

The work of the two answers matches the earlier rounds, so the fall is not a smaller answer: this
round wrote 499 visible tokens for the long prompt, the same as every round of 09-23, and 621.5
output tokens of which 122.5 were reasoning, inside the range that those rounds held. The slower
rate is a slower decode, not less work.

## Limits

- One round, 1 to 5 samples for each phase. The `models` and `models_reuse` rows have 3 samples and
  the concurrent summary has 1. A difference below 10 percent is noise, and the quotients above
  are far outside it.
- The comparison against 2026-09-23 crosses six days, a different hour and a different load of the
  provider. Read a quotient of two rounds as the state of the route at two moments, not as a
  property of the route; a rate of the model that a provider serves moves with the queue it holds.
- The round did not test retries, tool calls, or streaming with tools.
- The second round of this session, `../2026-09-29T062914Z/`, repeated the same command 47 seconds
  later and lands within 4 percent of every model-side row of this one.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `commandcode_20260929T062827Z.json` | 2026-09-29T06:28:27Z | 21 records in the `{meta, records}` format, phases transport, short, long, concurrent. |

The other round of 2026-09-29 is in `../2026-09-29T062914Z/`. The four rounds of 2026-09-23 are in
`../2026-09-23T153444Z/`, `../2026-09-23T204204Z/`, `../2026-09-23T210256Z/` and
`../2026-09-23T212350Z/`; `../README.md` indexes all of them and `../../ANALYSIS.md` compares them.
