# Results: deepseek-v4.1-flash on CommandCode and on OpenCode (Go)

Date: 2026-09-23 (CEST). Machine: macOS 26.6.2. Client: `curl` with a browser user agent. The two sides ran in the same session and in overlapping windows, in an interleaved A/B order.

Both routes serve the same model. CommandCode names it `deepseek/deepseek-v4.1-flash`. OpenCode names it `deepseek-v4.1-flash`.

- CommandCode: 18 clean requests in the A/B test, plus 55 requests in the first characterization session.
- OpenCode (Go): 18 clean requests in the A/B test, plus 4 parallel requests.
- The tool reads each token count from the `usage` block of the response. It never counts SSE lines.

## Comparison of the two routes

The A/B test alternated the two endpoints. The table gives the median value of each measurement.

| Measurement | CommandCode | OpenCode (Go) | OpenCode divided by CommandCode |
|---|---|---|---|
| TLS handshake, new connection | 24 ms | 200 ms | 8.4 times |
| TTFB of `/models`, new connection | 47 ms | 460 ms | 9.7 times |
| TTFB of `/models`, reused connection | 20 ms | 265 ms | 13 times |
| Short answer: TTFT of the first token | 912 ms | 1561 ms | 1.71 times |
| Short answer: TTFT of the visible token, and total time | 1044 ms and 1046 ms | 1785 ms and 1792 ms | 1.71 times |
| Long answer of 620 tokens: TTFT of the first token | 884 ms | 2052 ms | 2.32 times |
| Long answer of 620 tokens: TTFT of the visible token | 1511 ms | 3033 ms | 2.01 times |
| Long answer of 620 tokens: total time | 2673 ms | 4948 ms | 1.85 times |
| TPS of the sustained decoding | 360 tokens/s (343 to 364) | 230 tokens/s (199 to 269) | 1.56 times |
| TPS of the visible content | 439 tokens/s | 260 tokens/s | 1.69 times |
| TTFT with 18000 input tokens | 1671 ms | 3774 ms | 2.26 times |
| 4 parallel requests: rate of one request | 378 tokens/s (373 to 385) | 233 tokens/s (215 to 259) | 1.63 times |
| 4 parallel requests: total rate | 947 tokens/s and 1.66 requests/s | 476 tokens/s and 0.81 requests/s | 2.0 times |

## Cause of the difference

The row of the reused connection comes from another window than the rest of the table above. `bench_py_example_commandcode_20260923T150937Z.json` holds its three CommandCode requests, and the OpenCode side of that row was measured in a window whose records this directory does not hold. Every other row of the table holds the records of the A/B test.

The gateway of OpenCode adds a fixed overhead of about 245 ms to each request, and the network does not cause it. With a ready socket, which three requests inside one `curl` command give, `/models` needs 265 ms on OpenCode and 20 ms on CommandCode. That overhead is 38 percent of the gap in the TTFT of a short answer, or 249 ms of 649 ms.

The rest of the gap comes from the queue and the start of the model. OpenCode serves the same model about 1.6 times slower in the sustained decoding.

The amount of work is comparable on both sides. The answers hold 619 tokens on one side and 650 on the other, with 120 and 150 reasoning tokens. The same answer needs 2.7 seconds on CommandCode and 4.9 seconds on OpenCode.

The queue varies more on OpenCode. The TTFT ran from 1511 ms to 2580 ms on OpenCode, and from 800 ms to 1027 ms on CommandCode.

## Parallel requests

| Endpoint | One request | 4 parallel requests, total | Requests each second |
|---|---|---|---|
| CommandCode | 346 tokens/s and 0.23 requests/s | 947 tokens/s | 1.66 |
| OpenCode (Go) | not measured | 476 tokens/s | 0.81 |

With 4 parallel requests, both endpoints keep the rate of one request. CommandCode gave 378 tokens/s against 346 tokens/s for a single request. OpenCode gave 233 tokens/s against a single-request rate of 230 tokens/s. The bottleneck holds at least 4 parallel requests.

## Findings about the model

The findings below apply to both endpoints.

- The model always reasons first. Even the prompt `Reply with exactly: pong` spends 10 to 14 reasoning tokens before the answer. A long answer spends 47 to 668 reasoning tokens before the content, with a median of about 380, or about 43 percent of the output.
- The value `thinking: {"type": "disabled"}` does not stop the reasoning. The parameter `reasoning_effort` with the values `low` and `high` showed no difference. The gateway appears to ignore both parameters on these routes.
- The prefill is cheap. In the first session, an input of 637 tokens gave a TTFT of 944 ms. An input of 18037 tokens gave 1015 ms, a difference of 71 ms inside the noise. The TTFT is the queue and the start of the reasoning.
- In the later A/B session, a large input did add delay. The TTFT with 18000 input tokens was 1671 ms on CommandCode and 3774 ms on OpenCode. The queue of the provider dominates and changes between windows.

## Limits

- Each measurement has 1 to 6 samples in a short window of about 10 minutes, so a difference below 10 percent is noise.
- The rate depends on the type of output. The prompts asked for a list of numbers. Prose and code can give other rates.
- The campaign did not test retries, tool calls, or streaming with tools. A gateway can behave in another way in those cases.
- The value `tok_per_s_visible` has no meaning for an answer of 3 tokens, because the result is a large number. Read it for long answers only.

## Raw data in this directory

| File | Generated (UTC) | Content |
|---|---|---|
| `commandcode_single_20260923.json` | 2026-09-23, time not recorded | The full characterization of CommandCode, with 55 records: transport, short answer, medium answer, streaming, prefill, 1 and 4 parallel requests, and the thinking toggle. |
| `ab_commandcode_20260923.json` | 2026-09-23, time not recorded | The A/B test, CommandCode side, with 18 records. |
| `ab_opencode-go_20260923.json` | 2026-09-23, time not recorded | The A/B test, OpenCode (Go) side, with 18 records. |
| `bench_py_example_commandcode_20260923T150937Z.json` | 2026-09-23T15:09:37Z | The output of `bench.py run` over transport, short, long, prefill and concurrent, with 19 records in the `{meta, records}` format. It is the only file of this session with a `meta` block, and the only source of the row of the reused connection. |

The scripts of this session wrote the three files above that hold a bare list of records, so their time of the day is not recorded. The campaign of Windows 11 is in the directory `../2026-09-23T153444Z/`.
