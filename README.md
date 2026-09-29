# llm-endpoint-bench

`bench.py` measures one OpenAI-compatible model endpoint against another: latency, throughput, and
tokens per second. It sends each request with `curl`, so no client library hides the slow end of
the distribution, and it reads the token counts from the `usage` block of the response. It uses
the standard library of Python only.

## Results

Three routes serve one model, `deepseek-v4.1-flash`: the API of the vendor of that model, and two
gateways that resell it, CommandCode and OpenCode (Go). Eight rounds measured them on one Windows 11
host, and the tool makes two comparisons of them:

- **CommandCode against OpenCode (Go)**, four rounds on 2026-09-23, twenty minutes to four hours
  apart. CommandCode is faster on every measurement of every round: the gateway of OpenCode adds 250
  to 325 ms to each request with a ready socket, nine to twenty times the cost of CommandCode, and
  OpenCode decodes about 1.6 times slower in the steady state.
- **The vendor route against CommandCode**, one interleaved round on 2026-09-29. CommandCode wins
  every row of the transport, 18.5 ms against 260.7 ms for a request on a ready socket, and the
  vendor route wins every row of the model: a short answer at 0.65 s of TTFT against 1.65 s, and a
  sustained decode of 373.2 tokens/s against 201.0. The edge of the vendor route is expensive and
  its model is fast; the gateway of CommandCode is the other way round, so a route is not faster
  than another without naming the half of it that you pay for.

The rounds of 2026-09-29 also measured the CommandCode route alone at 06:28Z and 06:29Z, six days
after the four rounds before it: its transport held at the fast end of its range and the model side
of it ran at about half the rate, 192.4 and 185.4 tokens/s against 362.9 to 378.0, and a short
answer at 1.62 and 1.64 s of TTFT against 0.75 to 0.84 s. OpenCode (Go) could not be measured that
day: its subscription refused every completion with `403` while the transport of the route went on
answering.

The tables of each round, the analysis of the differences and the limits of the measurements are in
`ANALYSIS.md`; the raw records are in `results/`, and `results/README.md` indexes them.

## Requirements

`python` and `curl`, and a key of each endpoint that you measure. A key is looked for in four
places, and the first one that holds it wins:

| Place | Note |
|---|---|
| The environment of the process | A `COMMANDCODE_API_KEY=... python bench.py list` wins over everything |
| The user environment of Windows | The registry value of `HKCU\Environment`, which a process that a desktop app started does not inherit |
| A `.env` file beside the tool | Already in `.gitignore`, and the place to put a key for one route |
| The profile of the Hermes Agent desktop app | Its two `.env` paths are read; its credential pool holds a fingerprint and not a value |

The tool prints the name of the key variable and the place it came from, never the value.

| Endpoint | Base URL | Model | Key variable | Extra header |
|---|---|---|---|---|
| `commandcode` | `https://api.commandcode.ai/provider/v1` | `deepseek/deepseek-v4.1-flash` | `COMMANDCODE_API_KEY` | none |
| `opencode-go` | `https://opencode.ai/zen/go/v1` | `deepseek-v4.1-flash` | `OPENCODE_GO_API_KEY`, or `OPENCODE_API_KEY` | `x-opencode-session` |
| `deepseek-official` | `https://api.deepseek.com/v1` | `deepseek-flash` | `DEEPSEEK_API_KEY` | none |

The last row is the API of the vendor of the model, which the two gateways above resell: the same
model with no reseller in the path, under the id that the vendor gives it. `python bench.py list`
prints this table and says whether each key resolves and where it found it. A route other than these
three takes one entry in `ENDPOINTS` at the top of `bench.py`, and any pair of them can be measured
against each other:

```python
"example": {"base_url": "https://api.example.com/v1", "model": "vendor/model-id",
            "key_env": "EXAMPLE_API_KEY", "key_env_alt": ["EXAMPLE_KEY"], "session_header": False},
```

## How to run it

```bash
python bench.py list                                        # the routes and their keys
python bench.py ab --a commandcode --b opencode-go --n 4     # the A/B test, all four phases
python bench.py ab --a deepseek-official --b commandcode
python bench.py run --endpoint deepseek-official             # one route on its own
python bench.py report results/2026-09-23T210256Z            # one file, or every file of a directory
python bench.py compare results/2026-09-23T210256Z           # the two sides of the last run in it
python bench.py compare results/2026-09-29T064339Z/ab_commandcode_20260929T064339Z.json \
                       results/2026-09-29T064339Z/ab_deepseek-official_20260929T064339Z.json
```

`ab` alternates the two endpoints, so the load of the provider hits both sides in the same way, and
`--n` is the number of rounds of the `short` and `long` phases (5 and 4 requests each). It prints
one line for each request as it arrives. Files land in a new directory named for the time of the
run in UTC, `results/<date>T<time>Z/`, so a second run of the same day cannot mix with the first
one; `--out-dir` puts the files of several commands in one directory of a round. `run
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
  delay before the first visible token. The difference is the slow start that a user sees, and it
  moves with the reasoning that precedes the visible text, so read it next to `reasoning_tokens`.
- `tok_per_s_total` divides the output tokens by the time from the first delta to the last one, and
  it includes the reasoning; `tok_per_s_visible` counts the visible content only. `models_reuse`
  gives the TTFB with a ready socket, which is the fixed cost of the gateway for each request.
- A rate divides tokens by time, so two routes that write a different number of tokens for the same
  prompt are not compared by it alone. `compare` says so under its table when the two sides differ
  by more than a fifth; the row that survives that case is `tok_per_s_visible`, which divides the
  same visible answer by the time on both sides.
- `compare` prints the median of each metric of the two sides, the quotient, the number of samples
  of each side, and the faster endpoint. It names no winner for a count, for a difference below 10
  percent, or for a phase of fewer than 3 samples, and it hides a rate whose median answer is too
  short to hold one. It prints those rules under its table, so a reader of the table has them.

## Layout of the repository

```
bench.py                  the runner: the phases, the A/B runner, the report, the comparison.
ANALYSIS.md               the analysis of the results of the rounds.
results/                  one directory for each round, with its summary and its records.
results/README.md         the index of the rounds and the format of a result file.
```

`bench.py` is the only source file. The first version of each tool is in the history of the
repository (`git log --oneline`): every measurement that survived is a phase of `bench.py`, and the
aggregations of the first session are the commands `report` and `compare`.

## Pitfalls

- Send the answers as a stream. Without streaming, the TTFB and the total time are the same value,
  and a rate computed from a non-streaming answer is not correct.
- OpenCode (Go) requires the header `x-opencode-session`, else the answer is `400 MissingSessionID`,
  and it refuses `urllib` of Python with `403`: send a browser user agent, as `bench.py` does.
- The tool speaks the OpenAI-compatible surface of a route, `POST /chat/completions`. The vendor
  route also answers on `POST /anthropic/v1/messages`, which this tool does not measure and whose
  numbers are therefore not rows of these tables.
- A key that the user set for the whole account on Windows lives in the registry and not in the
  environment of a process that a desktop app started: read it as `bench.py` does, or the tool
  reports the route as `MISSING` while its key is present on the machine.
- A route can authenticate and list its models while it refuses every completion: OpenCode (Go) did
  that on 2026-09-29, `403 An active OpenCode Go subscription is required to use Go models`, with
  `/models` answering `200` all the while. Such a request is an error in a result file, with its
  status and a sample of the body beside it, and it stays out of every median.
- Compare a rate in tokens, not in seconds, because two endpoints do not write the same number of
  tokens for the same prompt; and read a ratio against the other ratios of its own table, not
  against the absolute values of another run.

## License

MIT. See `LICENSE`.
