# Results: deepseek-flash on the two surfaces of its vendor, Windows 11, 07:45Z

The run started at 2026-09-29T07:45:29Z (09:45 local time). Machine: Windows 11, host
`DESKTOP-08PBEHO`. Client: `curl` with a browser user agent. The two sides are the two surfaces of
one service, run in the same session in an interleaved A/B order:

```
python bench.py ab --a deepseek-official --b deepseek-official-messages --n 4
```

- `deepseek-official` — `POST /v1/chat/completions` on `https://api.deepseek.com/v1`, the
  OpenAI-compatible surface, 48 clean requests, no error.
- `deepseek-official-messages` — `POST /v1/messages` on `https://api.deepseek.com/anthropic`, the
  Messages surface, 48 clean requests, no error.
- Both sides carry the same model id, `deepseek-flash`, and the same key.
- The phases `transport`, `short`, `long` and `concurrent` ran on both sides. Each phase has 3, 20,
  16 and 4 samples for a side, plus the concurrent summary.

This is the first round of the tool that measures both surfaces. The two of them are not the same
request, and the round exists to say which rows of a comparison of them hold that difference and
which do not.

## Comparison of the two surfaces

The table gives the median value of each measurement. A value below 1 in the last column belongs to
a rate, where a large number is better. `-` is a row that one surface cannot fill.

| Measurement | OpenAI-compatible | Messages | Messages divided by OpenAI-compatible |
|---|---|---|---|
| DNS of the probe | 20.6 ms | 8.6 ms | 0.42 |
| TCP connect, new connection | 30.1 ms | 17.6 ms | 0.58 |
| TLS handshake, new connection | 43.8 ms | 31.2 ms | 0.71 |
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
| Long answer: TPS of the visible content | 438.1 tokens/s | - | - |
| 4 parallel requests: rate of one request | 359.0 tokens/s | 361.8 tokens/s | 1.01 (same) |
| 4 parallel requests: total rate | 780.9 tokens/s | 672.9 tokens/s | 0.86 |
| Long answer: reasoning tokens | 111 | - | - |
| Long answer: output tokens | 611 | 642 | 1.05 |
| Long answer: content tokens | 500 | - | - |

The tool names no difference between the two surfaces on any row of a phase of the model: every
delay, every total and the sustained rate of the eight model-side rows come out `same` at a
threshold of 10 percent, from the short answer, 673.6 against 695.4 ms, to the rate of one request
under load, 359.0 against 361.8 tokens/s. What separates the two columns is in the transport and in
the rows that one surface does not report.

## What the differences come from

- The rows of the transport are not the same measurement on the two sides, and the round says so in
  the record of each one: the OpenAI-compatible surface is probed with `GET /models`, a body of no
  tokens, and the Messages surface with the smallest message that it takes, one token, streamed. The
  TTFB of the two probes is within 26 percent of each other on a new connection, 300.4 against
  378.6 ms, and within 7 percent on a ready socket, 312.7 against 289.7 ms; the total time of the
  probe is not comparable at all, 300.5 against 693.4 ms, because the second probe waits for the
  model to write its one token. The three rows of the handshake move the other way, 20.6 against
  8.6 ms of DNS, 30.1 against 17.6 of TCP and 43.8 against 31.2 of TLS, and they hold no claim
  about the surfaces: they measure the path to each host of the service at one moment.
- The Messages surface reports no reasoning split of its output tokens. Three rows of the table are
  therefore empty on its side — `reasoning_tokens`, `content_tokens` and `tok_per_s_visible`, the
  last because its numerator is `content_tokens` — and the tool names them under its table rather
  than leaving a dash to be read as a zero. The rate of the sustained decoding, which divides the
  output tokens of the whole answer by the time of its generation, is the rate that both sides can
  hold, and the two agree: 367.2 against 356.5 tokens/s.
- The work of the answers is close but not equal: the `long` phase wrote 611 output tokens on the
  OpenAI-compatible side and 642 on the Messages one, 5 percent apart, and the `concurrent_4` phase
  644 against 585.5. Neither difference crosses the fifth of the tool's work warning, so a rate of
  those phases is a rate of the route and not of a longer answer. The counts do not say how much of
  that output was reasoning on the Messages side, because that surface does not say.
- The one row of the model that is not `same` is the aggregate rate of 4 parallel requests, 780.9
  against 672.9 tokens/s, a quotient of 0.86, and the tool names no winner for it: one sample of a
  summary is not a measurement. The per-request rate of the same phase, 359.0 against 361.8
  tokens/s, held the rate of one long answer alone on both sides, 367.2 and 356.5 tokens/s, so 4
  parallel requests cost neither surface its rate in this round.

## What this round settles

- The surface that a client speaks does not change the latency of the model behind it. A user of
  this service reads the same first token, the same visible start and the same sustained rate
  through `/v1/chat/completions` and through `/v1/messages`, inside the 10 percent noise of these
  measurements.
- What a surface changes is what a client can learn. The OpenAI-compatible one reports the reasoning
  split and the count of the visible content; the Messages one reports two counts and no split, so
  the rate of the visible content cannot be read from it at all.
- The transport of a route is measured by a probe, and the probe of each surface is a different
  request. Read the transport rows of two surfaces as two readings of the path at one moment, not as
  a difference between the surfaces.

## Limits

- One round, in an interleaved A/B order. 3 to 20 samples for each phase and each side, one host,
  and the two sides ran inside ten minutes of one morning. The `models` and `models_reuse` rows have
  3 samples and each concurrent summary has 1, so the tool prints no verdict for a phase of one
  sample. A difference below 10 percent is noise.
- The probes of the two transport phases are not the same request, as the section above states, and
  the round is the first of the tool to measure a Messages surface at all.
- The Messages surface of this service reports no reasoning split, so three rows of its side of the
  table are empty by the nature of the surface and not by a fault of the round.
- The round did not test retries, tool calls, or streaming with tools.
- The keys of the two sides are the same key, read from the environment of the process or from
  `.env` beside the tool, which is in `.gitignore`; no result file and no summary holds one.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `ab_deepseek-official_20260929T074529Z.json` | 2026-09-29T07:45:29Z | The A/B test, OpenAI-compatible side, 48 records, `api` = `openai-completions`. |
| `ab_deepseek-official-messages_20260929T074529Z.json` | 2026-09-29T07:45:29Z | The A/B test, Messages side, 48 records, `api` = `anthropic-messages`. |

The rounds of the vendor route against CommandCode are in `../2026-09-29T064339Z/` and
`../2026-09-29T063619Z/`; the rounds of the two resold routes are in the directories of
2026-09-23 and 2026-09-29; `../README.md` indexes all of them and `../../ANALYSIS.md` compares them.
