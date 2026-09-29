# Results: deepseek-v4.1-flash on CommandCode, its fast tier and the vendor, Windows 11, 11:58Z

The run started at 2026-09-29T11:58:01Z (13:58 local time). Machine: Windows 11, host
`DESKTOP-08PBEHO`. Client: `curl` with a browser user agent. Three endpoints ran in one interleaved
session, so the load of the providers hit every side the same way:

```
python bench.py ab --a commandcode --b deepseek-official --c commandcode-fast --n 4
```

- `commandcode` — `deepseek/deepseek-v4.1-flash` on `https://api.commandcode.ai/provider/v1`,
  48 clean requests, no error.
- `commandcode-fast` — `deepseek/deepseek-v4.1-flash-fast` on the same base URL, 48 clean requests,
  no error. This is the fast tier of the same reseller, and the first round of this repository to
  measure it.
- `deepseek-official` — `deepseek-flash` on `https://api.deepseek.com/v1`, the API of the vendor of
  the model, 48 clean requests, no error.
- The phases `transport`, `short`, `long` and `concurrent` ran on all three sides. Each phase has 3,
  20, 16 and 4 samples for a side, plus the concurrent summary.

This is the first round of the tool with three endpoints in it, and the first that reads two model
ids of one reseller. The three files of the directory are three sides of one session, so every pair
of them is a comparison of one session and not a quotient read across two runs.

## The medians of the three sides

| Measurement | `commandcode` | `commandcode-fast` | `deepseek-official` |
|---|---|---|---|
| DNS of `/models` | 13.4 ms | 10.2 ms | 6.2 ms |
| TCP connect, new connection | 22.0 ms | 19.9 ms | 16.4 ms |
| TLS handshake, new connection | 43.2 ms | 36.9 ms | 31.3 ms |
| TTFB of `/models`, new connection | 62.1 ms | 55.5 ms | 307.4 ms |
| TTFB of `/models`, reused connection | 16.4 ms | 15.9 ms | 253.3 ms |
| Short answer: TTFT of the first token | 1777.3 ms | 939.4 ms | 715.0 ms |
| Short answer: TTFT of the visible token | 1851.4 ms | 1110.7 ms | 801.6 ms |
| Short answer: total time | 1867.2 ms | 1124.8 ms | 805.0 ms |
| Long answer: TTFT of the first token | 1655.0 ms | 925.5 ms | 751.8 ms |
| Long answer: TTFT of the visible token | 3718.2 ms | 1343.7 ms | 1581.3 ms |
| Long answer: total time | 5647.6 ms | 2500.4 ms | 2648.4 ms |
| Long answer: TPS of the sustained decoding | 217.8 tokens/s | 370.1 tokens/s | 367.6 tokens/s |
| Long answer: TPS of the visible content | 247.9 tokens/s | 446.6 tokens/s | 442.7 tokens/s |
| 4 parallel requests: rate of one request | 206.2 tokens/s | 361.4 tokens/s | 368.2 tokens/s |
| 4 parallel requests: total rate | 447.4 tokens/s, 0.7 req/s | 808.6 tokens/s, 1.3 req/s | 930.8 tokens/s, 1.1 req/s |

## The three comparisons of one session

Each cell is the second endpoint of the pair divided by the first, as the `compare` command prints
it. On a delay a value below 1 means that the second endpoint is the faster one; on a rate it means
that the first is the faster one.

| Measurement | fast ÷ `commandcode` | vendor ÷ fast | vendor ÷ `commandcode` |
|---|---|---|---|
| TTFB of `/models`, reused connection | 0.97 (same) | 15.93 | 15.45 |
| Short answer: TTFT of the first token | 0.53 | 0.76 | 0.40 |
| Short answer: TTFT of the visible token | 0.60 | 0.72 | 0.43 |
| Short answer: total time | 0.60 | 0.72 | 0.43 |
| Long answer: TTFT of the first token | 0.56 | 0.81 | 0.45 |
| Long answer: TTFT of the visible token | 0.36 | 1.18 | 0.43 |
| Long answer: total time | 0.44 | 1.06 (same) | 0.47 |
| Long answer: TPS of the sustained decoding | 1.70 | 0.99 (same) | 1.69 |
| Long answer: TPS of the visible content | 1.80 | 0.99 (same) | 1.79 |
| 4 parallel requests: rate of one request | 1.75 | 1.02 (same) | 1.79 |
| 4 parallel requests: total rate | 1.81 | 1.15 | 2.08 |

- **The fast tier of CommandCode is real, and it is worth about twice the normal one.** Every row of
  a phase of the model moves the same way, by 1.70 to 1.81 times on the rates and to 0.36 to 0.60 on
  the delays: a short answer of 939.4 ms against 1777.3 ms, the first visible token of a long answer
  at 1343.7 ms against 3718.2 ms, and a sustained decoding of 370.1 tokens/s against 217.8. The two
  model ids share one base URL, one key and one edge (15.9 and 16.4 ms on a ready socket, `same`),
  so the whole difference is on the model side of that reseller.
- **The fast tier and the vendor of the model are one measurement apart.** Every rate comes out
  `same` within 10 percent — 370.1 against 367.6 tokens/s sustained, 446.6 against 442.7 on the
  visible content, 361.4 against 368.2 for one request under load — and so does the total time of a
  long answer, 2500.4 against 2648.4 ms. The vendor wins the short answer, 715.0 ms against
  939.4 ms, by 1.31 times, and the fast tier wins the start of a long answer, 1343.7 ms against
  1581.3 ms, by 1.18 times. The two differ in what they charge for the edge and for a token, not in
  what the model costs.
- **The two halves of a route are visible in one table.** The reused-socket TTFB separates them: the
  vendor charges 253.3 ms for a request with a ready socket where CommandCode charges 15.9 to
  16.4 ms, 15 to 16 times less. That is the same split that the round of 06:43Z found, and the fast
  tier is the endpoint of this round that holds both halves at once: the edge of the reseller and a
  decode at the rate of the vendor.
- The normal tier of CommandCode is where this round's slower numbers are. Its short answer of
  1777.3 ms is the highest that this host has recorded on that route — the rounds of 06:28Z, 06:29Z
  and 06:43Z held 1616.9, 1638.7 and 1651.6 ms — while the vendor held 653.8 to 779.1 ms across the
  morning and 715.0 ms in this round. Both routes repeated themselves, so the gap is a property of
  the two model paths at this hour, not of the hour itself.
- The work of the three sides is not the same, and the tool says so under its table for two of the
  three pairs. In the `long` phase the normal tier wrote 896 output tokens of which 397 were
  reasoning, against 590 and 90 for the fast tier and 635 and 135 for the vendor: 1.52 times the
  output of the fast tier, and several of its answers stopped at the 1200-token cap of the phase. In
  the `concurrent_4` phase the vendor wrote 896 output tokens of which 396 were reasoning, against
  614 and 115 for the normal tier and 597 and 97 for the fast one. The visible content is the same
  499 and 500 tokens on all three sides and in both phases, so the rate to read across them is the
  visible one, 247.9 against 446.6 and 442.7 tokens/s in the `long` phase and 258.6 against 439.9
  and 443.4 under load. A shorter answer from one route is not evidence of a faster one.

## What the three cost

Catalog prices of 2026-09-29, USD per 1M tokens. The two CommandCode rows are from the models.dev
card of that provider; the vendor row is from the pricing page of DeepSeek, which halves its prices
outside the peak window (01:00 to 04:00 and 06:00 to 10:00 UTC, Monday to Friday, Chinese public
holidays excluded). This round ran at 11:58Z, outside that window.

| Endpoint | Input (cache miss) | Output | Cache read |
|---|---|---|---|
| `commandcode` | $0.15 | $0.60 | $0.003 |
| `commandcode-fast` | $0.16 | $0.58 | $0.016 |
| `deepseek-official`, off-peak | $0.15 | $0.60 | $0.003 |
| `deepseek-official`, peak | $0.30 | $1.20 | $0.006 |

- The fast tier buys its 1.70 to 1.81 times of throughput with 6.7 percent on the input, 5.3 times
  on a cache read and a 3.3 percent saving on the output. On a long agent session, where the cache
  read is most of the prompt, that is about 15 percent more expensive; it goes the other way only
  above roughly 0.5 to 0.65 output tokens for each token of prompt, which an agent does not reach.
- The vendor and the normal tier of CommandCode are the same price off-peak, and the vendor doubles
  inside its peak window while the reseller does not move.

## Limits

- One round, in an interleaved order of three endpoints. 3 to 20 samples for each phase and each
  side, one host, and the three sides ran inside 20 minutes of one afternoon. The `models` and
  `models_reuse` rows have 3 samples and each concurrent summary has 1, so the tool prints no
  verdict for a phase of one sample. A difference below 10 percent is noise.
- The `long` phase held a different amount of work on the three sides, as the section above states,
  and some answers of the normal tier stopped at the cap of the phase. Read a rate of that phase
  next to the token counts of the same row and prefer `tok_per_s_visible`.
- The prices above are catalog prices of one day, and the vendor moves its own by a factor of two
  across the day. They are a property of the catalogs, not of this round's records.
- The round did not test retries, tool calls, or streaming with tools.
- The three endpoints read their keys from the environment of the process or from `.env` beside the
  tool, which is in `.gitignore`; no result file and no summary holds one.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_commandcode_20260929T115801Z.json` | 2026-09-29T11:58:01Z | `commandcode`, 48 records, phases transport, short, long and concurrent. |
| `ab_commandcode-fast_20260929T115801Z.json` | 2026-09-29T11:58:01Z | `commandcode-fast`, 48 records and the same phases. |
| `ab_deepseek-official_20260929T115801Z.json` | 2026-09-29T11:58:01Z | `deepseek-official`, 48 records and the same phases. |

`compare` takes any two of the three by name. The rounds of this morning are in
`../2026-09-29T062827Z/`, `../2026-09-29T062914Z/`, `../2026-09-29T063619Z/` and
`../2026-09-29T064339Z/`; `../README.md` indexes all of them and `../../ANALYSIS.md` compares them.
