# Results: deepseek-v4.1-flash on CommandCode, Windows 11, 06:29Z

The run started at 2026-09-29T06:29:14Z (08:29 local time), 47 seconds after the round of
`../2026-09-29T062827Z/`, on the same host `DESKTOP-08PBEHO` and the same route. The command was
the same:

```
python bench.py run --endpoint commandcode
```

The second round exists to separate the state of the route from the noise of one round: two rounds
of the same command, back to back, show which rows of the first one are stable.

- 21 clean records, no error, in the same four phases.
- The `long` answers hold 499 and 500 visible tokens, the same content as every other round.

## The medians of this round

| Measurement | Median | Min | Max | n |
|---|---|---|---|---|
| DNS of `/models` | 5.7 ms | 4.7 ms | 16.3 ms | 3 |
| TCP connect, new connection | 14.7 ms | 12.6 ms | 26.1 ms | 3 |
| TLS handshake, new connection | 33.3 ms | 27.9 ms | 44.7 ms | 3 |
| TTFB of `/models`, new connection | 54.1 ms | 43.1 ms | 66.5 ms | 3 |
| TTFB of `/models`, reused connection | 14.0 ms | 12.6 ms | 48.3 ms | 3 |
| Short answer: TTFT of the first token | 1638.7 ms | 1491.1 ms | 1698.9 ms | 5 |
| Short answer: TTFT of the visible token | 1768.1 ms | 1646.0 ms | 1812.2 ms | 5 |
| Short answer: total time | 1773.9 ms | 1649.7 ms | 1876.0 ms | 5 |
| Long answer: TTFT of the first token | 2160.9 ms | 1710.7 ms | 2465.0 ms | 4 |
| Long answer: TTFT of the visible token | 3426.9 ms | 3064.1 ms | 4635.6 ms | 4 |
| Long answer: total time | 5611.7 ms | 5257.8 ms | 7003.0 ms | 4 |
| Long answer: TPS of the sustained decoding | 185.4 tokens/s | 152.2 | 204.9 | 4 |
| Long answer: TPS of the visible content | 227.7 tokens/s | 212.9 | 230.9 | 4 |
| 4 parallel requests: rate of one request | 201.6 tokens/s | 197.0 | 202.7 | 4 |
| 4 parallel requests: total rate | 481.6 tokens/s, 0.82 requests/s | - | - | 1 |

## The two rounds of 2026-09-29

| Measurement | 06:28Z | 06:29Z | 06:29 divided by 06:28 |
|---|---|---|---|
| TLS handshake, new connection | 38.6 ms | 33.3 ms | 0.86 |
| TTFB of `/models`, reused connection | 14.6 ms | 14.0 ms | 0.96 |
| Short answer: TTFT of the first token | 1616.9 ms | 1638.7 ms | 1.01 |
| Short answer: total time | 1785.5 ms | 1773.9 ms | 0.99 |
| Long answer: TTFT of the visible token | 2758.0 ms | 3426.9 ms | 1.24 |
| Long answer: total time | 5197.1 ms | 5611.7 ms | 1.08 |
| Long answer: TPS of the sustained decoding | 192.4 tokens/s | 185.4 tokens/s | 0.96 |
| Long answer: TPS of the visible content | 224.2 tokens/s | 227.7 tokens/s | 1.02 |
| 4 parallel requests: rate of one request | 199.8 tokens/s | 201.6 tokens/s | 1.01 |

Eight of the nine rows agree within 5 percent, and the one that does not is the delay to the first
visible token of a long answer, 2758.0 against 3426.9 ms: the floor of the visible answer moves
with the number of reasoning tokens that the model writes before it, 122.5 in the first round
against 152.0 here, and 277 at the worst sample of this one. The stable rows are the ones behind
the latency a user feels: the short answer, the sustained rate and the rate under load.

## Limits

- Two rounds, 1 to 5 samples for each phase, back to back: they measure one hour of one day.
- The delay to the first visible token of a long answer is the least stable row of this pair. Read
  it against the reason for it, the reasoning tokens that the answer spends before it becomes
  visible, and not as a property of the route.
- Neither round tested retries, tool calls, or streaming with tools.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `commandcode_20260929T062914Z.json` | 2026-09-29T06:29:14Z | 21 records in the `{meta, records}` format, phases transport, short, long, concurrent. |

The first round of 2026-09-29 is in `../2026-09-29T062827Z/`, and it carries the table of this
route against the four rounds of 2026-09-23. `../README.md` indexes the directories and
`../../ANALYSIS.md` holds the comparison of the rounds.
