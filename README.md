# llm-endpoint-bench

`bench.py` measures one OpenAI-compatible model endpoint against another: latency, throughput, and
tokens per second. It sends each request with `curl`, so no client library hides the slow end of
the distribution, and it reads the token counts from the `usage` block of the response. It uses
the standard library of Python only.

## Results

CommandCode is faster than OpenCode (Go) on every measurement of every campaign. The gateway of
OpenCode adds 250 to 325 ms to each request with a ready socket, nine to twenty times the cost of
CommandCode, and OpenCode decodes about 1.6 times slower in the steady state.

Three campaigns measured this on one Windows 11 host, twenty minutes to four hours apart. Their
tables, the analysis of the differences and the limits of the measurements are in `ANALYSIS.md`;
the raw records are in `results/`, and `results/README.md` indexes them.

## Requirements

`python` and `curl`, and a key of each endpoint, in the environment or in a `.env` file in the
directory of the tool (which is already in `.gitignore`). A machine where the Hermes Agent desktop
app holds the keys is read too, from the profile of that app: that is the only tie between the two
programs. The tool prints the name of a key variable only, never its value.

| Endpoint | Base URL | Key variable | Extra header |
|---|---|---|---|
| `commandcode` | `https://api.commandcode.ai/provider/v1` | `COMMANDCODE_API_KEY` | none |
| `opencode-go` | `https://opencode.ai/zen/go/v1` | `OPENCODE_GO_API_KEY` | `x-opencode-session` |

`python bench.py list` prints this table and says whether each key resolves. A route other than
these two takes one entry in `ENDPOINTS` at the top of `bench.py`:

```python
"example": {"base_url": "https://api.example.com/v1", "model": "vendor/model-id",
            "key_env": "EXAMPLE_API_KEY", "session_header": False},
```

## How to run it

```bash
python bench.py ab --a commandcode --b opencode-go --n 4     # the A/B test, all four phases
python bench.py report results/2026-09-23T210256Z            # one file, or every file of a directory
python bench.py compare results/2026-09-23T210256Z           # the two sides of the last run in it
```

`ab` alternates the two endpoints, so the load of the provider hits both sides in the same way, and
`--n` is the number of rounds of the `short` and `long` phases (5 and 4 requests each). It prints
one line for each request as it arrives. Files land in a new directory named for the time of the
run in UTC, `results/<date>T<time>Z/`, so a second run of the same day cannot mix with the first
one; `--out-dir` puts the files of several commands in one directory of a campaign. `run
--endpoint NAME` measures one route on its own.

## Phases

| Phase | Requests | Purpose |
|---|---|---|
| `transport` | 3 new connections, 3 requests with a reused socket, 1 body request | Separates the handshake from the per-request overhead of the gateway, and confirms that the model id exists on the route |
| `short` | 5 streaming requests, `max_tokens=64` | The delay that a user feels on a short answer |
| `long` | 4 streaming requests, `max_tokens=1200` | The split of the TTFT and the sustained rate |
| `concurrent` | 4 parallel long answers | The rate of one request and the total rate under load |

## How to read the numbers

- `ttft_any_ms` is the delay before the first delta, reasoning or content; `ttft_content_ms` is the
  delay before the first visible token. The difference is the slow start that a user sees.
- `tok_per_s_total` divides the output tokens by the time from the first delta to the last one, and
  it includes the reasoning; `tok_per_s_visible` counts the visible content only. `models_reuse`
  gives the TTFB with a ready socket, which is the fixed cost of the gateway for each request.
- `compare` prints the median of each metric of the two sides, the quotient, the number of samples
  of each side, and the faster endpoint. It names no winner for a count, for a difference below 10
  percent, or for a phase of fewer than 3 samples, and it hides a rate whose median answer is too
  short to hold one. It prints those rules under its table, so a reader of the table has them.

## Layout of the repository

```
bench.py                  the runner: the phases, the A/B runner, the report, the comparison.
ANALYSIS.md               the analysis of the results of the campaigns.
results/                  one directory for each campaign, with its summary and its records.
results/README.md         the index of the campaigns and the format of a result file.
```

`bench.py` is the only source file. The first version of each tool is in the history of the
repository (`git log --oneline`): every measurement that survived is a phase of `bench.py`, and the
aggregations of the first session are the commands `report` and `compare`.

## Pitfalls

- Send the answers as a stream. Without streaming, the TTFB and the total time are the same value,
  and a rate computed from a non-streaming answer is not correct.
- OpenCode (Go) requires the header `x-opencode-session`, else the answer is `400 MissingSessionID`,
  and it refuses `urllib` of Python with `403`: send a browser user agent, as `bench.py` does.
- Compare a rate in tokens, not in seconds, because two endpoints do not write the same number of
  tokens for the same prompt; and read a ratio against the other ratios of its own table, not
  against the absolute values of another run.

## License

MIT. See `LICENSE`.
