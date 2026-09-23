# llm-endpoint-bench

This repository measures three properties of an OpenAI-compatible model endpoint: latency, throughput, and tokens per second (TPS).

The tool is `bench.py`. It sends each request with `curl`, so no client library retry hides the slow end of the distribution. It reads the token counts from the `usage` block of the response.

The directory `results/` holds one directory for each campaign, and each of them holds a `summary.md` and its raw records. `results/README.md` is the index of the campaigns.

## Results

CommandCode is faster than OpenCode (Go) on every measurement of every campaign. The gateway of OpenCode adds about 250 ms to each request with a ready socket, between 9 and 13 times the cost of CommandCode, and OpenCode decodes about 1.6 times slower in the steady state.

Three campaigns measured this: the first on macOS, then the same A/B test twice on Windows 11, four hours apart. The tables of each campaign, the analysis of the differences, what holds between the campaigns and the limits of the measurements are in `ANALYSIS.md`. The raw records are in `results/`.

## Requirements

You need `python3` and `curl`. The tool uses the standard library of Python only. The tool runs on Linux, macOS and Windows. On Windows, use `python` in place of `python3`, and run the commands from Git Bash, because the tool writes the body of a request with `--data-binary @-`.

The tool reads a key from the environment first. If the variable is absent, the tool reads the key from the file `~/.hermes/.env`, and on Windows also from `%LOCALAPPDATA%\hermes\.env`. The tool prints the name of a variable only, never the value.

| Endpoint name | Base URL | Variable of the key | Extra header |
|---|---|---|---|
| `commandcode` | `https://api.commandcode.ai/provider/v1` | `COMMANDCODE_API_KEY` | none |
| `opencode-go` | `https://opencode.ai/zen/go/v1` | `OPENCODE_GO_API_KEY` | `x-opencode-session` |

Run `python3 bench.py list` to print this table from the code.

## How to run the tool

1. Clone the repository and go to its directory.
2. Run `python3 bench.py list`. The command shows each known endpoint and the name of its key variable.
3. Run `python3 bench.py run --endpoint commandcode`. The command measures the transport, a short answer, a long answer, and a large input.
4. Run `python3 bench.py run --endpoint opencode-go`. The runner adds the session header for this endpoint.
5. Run `python3 bench.py run --endpoint commandcode --phases concurrent --concurrent 4`. The command measures 4 requests in parallel.
6. Run `python3 bench.py run --endpoint commandcode --phases thinking`. The command sends one long answer under each reasoning control, so it shows whether the route honours them.
7. Run `python3 bench.py ab --a commandcode --b opencode-go`. The command alternates the two endpoints, so the load of the provider hits both sides in the same way.
8. Run `python3 bench.py report results/2026-09-23T150937Z/ab_opencode-go_20260923.json`. The command prints the time of the run, the median, the minimum, and the maximum of each measurement.
9. Run `python3 bench.py compare results/2026-09-23T153444Z`. The command compares the two sides of the last run in that directory and prints one markdown table that holds the median of each metric of the two files, the quotient, the number of samples of each side and the name of the faster endpoint. The column `Better` stays empty for a count, for a difference below 10 percent, and for a phase with fewer than 3 samples on a side. Name two files in place of the directory for any other pair. Paste the table into a summary.

The command of the full campaign, as it ran for the summaries in `results/`:

```bash
python3 bench.py ab --a commandcode --b opencode-go \
  --phases transport,short,long,prefill,thinking,concurrent --n 4 --concurrent 4
```

Each run writes its files into a new directory that is named for the time of the run, as in `results/2026-09-23T161050Z/`, so a second run of the same day cannot mix with the first one. The name of the directory holds the time and nothing else; the host is in the `meta` block of each file and in the index `results/README.md`. The option `--out-dir` puts the files of more than one command in one directory, as the two campaigns in `results/` do. A file holds a `meta` block and the raw records, and its name and its `meta` block both hold the time of the run, as in `ab_commandcode_20260923T153444Z.json`. `results/README.md` is the index of the campaigns and states the format of a file. The commands `report` and `compare` print the time and the host of each file, and both of them take a directory as well as a file.

## How to measure another endpoint

1. Run the tool with the address, the name of the model, and the name of the key variable.
2. If the gateway requires the header `x-opencode-session`, add `--session-header`.
3. If you want a short name for the result file, add `--tag`.

```bash
python3 bench.py run \
  --base-url https://api.example.com/v1 \
  --model vendor/model-id \
  --key-env EXAMPLE_API_KEY \
  --tag example
```

## Manual requests

Use a manual request to make sure that a key and a name of a model are correct.

CommandCode:

```bash
curl -sS https://api.commandcode.ai/provider/v1/chat/completions \
  -H "Authorization: Bearer $COMMANDCODE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek/deepseek-v4.1-flash","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

OpenCode (Go). Without the session header, the endpoint answers `400 MissingSessionID`.

```bash
curl -sS https://opencode.ai/zen/go/v1/chat/completions \
  -H "Authorization: Bearer $OPENCODE_GO_API_KEY" \
  -H "x-opencode-session: $(python3 -c 'import uuid;print(uuid.uuid4())')" \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

The identifier of the model is different on each route. CommandCode uses the prefix of the provider, as in `deepseek/deepseek-v4.1-flash`. OpenCode uses the plain identifier, as in `deepseek-v4.1-flash`. Run `curl <base_url>/models` to list the identifiers of a route. The route `/models` of CommandCode is public.

## Use with Hermes Agent

Hermes Agent has a provider profile for each endpoint. Set `model.provider` to `commandcode` with `COMMANDCODE_API_KEY`, or to `opencode-go` (alias `go`) with `OPENCODE_GO_API_KEY`.

## Phases of the tool

| Phase | Requests | Purpose |
|---|---|---|
| `transport` | 3 new connections, 3 requests with a reused socket, and 1 body request | Separates the handshake from the overhead of the gateway, and confirms that the model id of the endpoint exists on the route |
| `short` | 5 streaming requests with `max_tokens=64` | Measures the delay that a user feels on a short answer |
| `long` | 4 streaming requests with `max_tokens=1200` | Measures the split of the TTFT and the sustained rate |
| `prefill` | 1 streaming request with about 18000 input tokens | Shows whether a large input changes the TTFT |
| `thinking` | 5 streaming requests with `max_tokens=400`, one for each reasoning control | Shows whether the route honours the toggle `thinking` and the parameter `reasoning_effort` |
| `concurrent` | N parallel requests | Measures the total rate and the rate of one request |

## Definitions of the measurements

- `ttft_any_ms` is the delay before the first delta of any kind, reasoning or content.
- `ttft_content_ms` is the delay before the first visible token. The difference between this value and `ttft_any_ms` is the delay that a user sees as a slow start.
- `tok_per_s_total` is `completion_tokens` divided by the time between the first delta and the last delta. The value includes the reasoning tokens.
- `tok_per_s_visible` is the number of content tokens divided by the time of the content phase.
- A rate needs a numerator. The tool prints neither rate for a phase whose median answer holds fewer than 50 output tokens (`tok_per_s_total`) or fewer than 10 content tokens (`tok_per_s_visible`): the window of a short answer is an edge of that answer, not a rate of decoding. The command `report` skips that line, and `compare` hides it when either side falls below the number.
- `models_reuse.ttfb_ms` is the TTFB with a ready socket. The value is the fixed cost of the gateway for each request.
- `models_body.n_ids` is the number of model ids of the route, and `models_body.target_present` says whether the model of this endpoint is one of them.
- `concurrent_summary.aggregate_tok_per_s` is the number of tokens of all requests divided by the wall clock time.

## Layout of the repository

```
bench.py                  the runner: the phases, the A/B runner, the report, the comparison.
ANALYSIS.md               the analysis of the results of the campaigns.
results/                  one directory for each campaign, with its summary and its records.
results/README.md         the index of the campaigns and the format of a result file.
```

`bench.py` is the only source file. The first version of each tool is in the history of the repository (`git log --oneline`). Every measurement that survived is a phase of `bench.py`, and the aggregations of the first session are the commands `report` and `compare`.

## Pitfalls

- Without streaming, the TTFB and the total time are the same value, because the body arrives in one piece. A rate that you compute from a non-streaming answer is not correct.
- The value `thinking: {"type": "disabled"}` does not stop the reasoning on these routes. The parameter `reasoning_effort` showed no effect. Do not expect a lower delay from these parameters. Run the phase `thinking` to measure this in your own window: it sends one long answer under each control. One sample proves nothing, because the number of reasoning tokens of a long answer changes between requests in any case.
- OpenCode (Go) requires the header `x-opencode-session`. Without the header, the answer is `400 MissingSessionID`. Send a browser user agent as well, because `urllib` of Python receives `403`.
- In `curl`, one flag `-o` with several URLs sends the second body to standard output. The body then joins the number of the flag `-w`. Use one `-o /dev/null` for each URL, as `bench.py` does. On Windows, curl is a native program and reads `NUL` in place of the mount `/dev/null`.
- Alternate the two endpoints in an A/B test. A sequence of all A requests and then all B requests mixes the result with the load of the provider.
- Compare the rate in tokens, not in seconds. Two endpoints do not send the same number of tokens for the same prompt.

## License

MIT. See `LICENSE`.
