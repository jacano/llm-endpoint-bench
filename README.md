# llm-endpoint-bench

`bench.py` measures one model endpoint against another: latency, throughput, and tokens per second.
An endpoint names one **surface** of a route, and the tool speaks the two that gateways serve:

- `openai-completions` — `POST /chat/completions`, the shape of the OpenAI API. The token counts of
  the answer, with the reasoning split out of them, arrive in a trailing `usage` block.
- `anthropic-messages` — `POST /v1/messages`, the shape of the Anthropic Messages API, with the key
  in `x-api-key` and a version header. The counts arrive split in two, the input at `message_start`
  and the output at `message_delta`; that surface reports no reasoning split, so the rows that need
  one (`reasoning_tokens`, `content_tokens`, `tok_per_s_visible`) are absent from a round of it.

It sends each request with `curl`, so no client library hides the slow end of the distribution, and
it reads each token count from the response of the surface. It uses the standard library of Python
only.

## Results

Three routes serve one model, `deepseek-v4.1-flash`: the API of the vendor of that model, on two
surfaces, and two gateways that resell it, CommandCode and OpenCode (Go). Nine rounds measured them
on one Windows 11 host, and the tool makes three comparisons of them:

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
- **The two surfaces of the vendor service against each other**, one interleaved round on
  2026-09-29, ten minutes after the one before it. Every row of a phase of the model comes out
  `same` within 10 percent — a short answer at 673.6 against 695.4 ms and a sustained decode of
  367.2 against 356.5 tokens/s — so the surface a client speaks does not change what the model
  costs. What it changes is what a client can read: the Messages surface reports no reasoning split,
  and three rows of its side of the table have no value at all.

The rounds of 2026-09-29 also measured the CommandCode route alone at 06:28Z and 06:29Z, six days
after the four rounds before it: its transport held at the fast end of its range and the model side
of it ran at about half the rate, 192.4 and 185.4 tokens/s against 362.9 to 378.0, and a short
answer at 1.62 and 1.64 s of TTFT against 0.75 to 0.84 s. OpenCode (Go) could not be measured that
day: its subscription refused every completion with `403` while the transport of the route went on
answering.

The tables of each round, the analysis of the differences and the limits of the measurements are in
`ANALYSIS.md`; the raw records are in `results/`, and `results/README.md` indexes them.

## Requirements

`python` and `curl`, on Windows, macOS or Linux, and nothing else: the standard library of Python
holds every other line of the tool. A result file is written as UTF-8 JSON with `\n` line endings,
so the same run produces the same bytes on any of the three, and the one platform detail that
`bench.py` carries is the null device that `curl` reads (`NUL` on Windows, `/dev/null` elsewhere).

A key of each endpoint that you measure is looked for in two places, and the first that holds it
wins:

| Place | Note |
|---|---|
| The environment of the process | A `COMMANDCODE_API_KEY=... python bench.py list` wins over everything |
| A `.env` file beside the tool | Keeps a key across runs, is already in `.gitignore`, and is the place to put a key |

Anywhere else a key may live — the environment of a shell that did not pass it on, the vault of a
desktop program — it is copied into that `.env` file by hand, which is one step and leaves the tool
with no dependency of its own. The tool prints the name of the key variable and the place it came
from, never the value.

| Endpoint | API | Base URL | Model | Key variable |
|---|---|---|---|---|
| `commandcode` | `openai-completions` | `https://api.commandcode.ai/provider/v1` | `deepseek/deepseek-v4.1-flash` | `COMMANDCODE_API_KEY` |
| `opencode-go` | `openai-completions` | `https://opencode.ai/zen/go/v1` | `deepseek-v4.1-flash` | `OPENCODE_GO_API_KEY`, or `OPENCODE_API_KEY` |
| `deepseek-official` | `openai-completions` | `https://api.deepseek.com/v1` | `deepseek-flash` | `DEEPSEEK_API_KEY` |
| `deepseek-official-messages` | `anthropic-messages` | `https://api.deepseek.com/anthropic` | `deepseek-flash` | `DEEPSEEK_API_KEY` |

`opencode-go` also requires the header `x-opencode-session`. The last two rows are the two surfaces
of one service, the API of the vendor of the model that the two gateways above resell: `/v1` is its
OpenAI-compatible path and `/anthropic` its Messages path. An endpoint takes **one** surface, so a
service of two takes two entries, and the tool can then put the surfaces of one service against each
other as readily as two services.

`python bench.py list` prints this table and says whether each key resolves and where it found it. A
route other than these four takes one entry in `ENDPOINTS` at the top of `bench.py`:

```python
"example": {"base_url": "https://api.example.com/v1", "model": "vendor/model-id",
            "api": OPENAI,  # or MESSAGES for a surface of the shape of POST /v1/messages
            "key_env": "EXAMPLE_API_KEY", "key_env_alt": ["EXAMPLE_KEY"], "session_header": False},
```

## How to run it

```bash
python bench.py list                                           # the routes, their surfaces and their keys
python bench.py ab --a commandcode --b opencode-go --n 4       # the A/B test, all four phases
python bench.py ab --a deepseek-official --b commandcode
python bench.py ab --a deepseek-official --b deepseek-official-messages   # the two surfaces of one service
python bench.py run --endpoint deepseek-official-messages      # one surface on its own
python bench.py report results/2026-09-23T210256Z              # one file, or every file of a directory
python bench.py compare results/2026-09-23T210256Z             # the two sides of the last run in it
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
| `transport` | 3 new connections, 3 requests with a reused socket, 1 body request | Separates the handshake from the per-request overhead of the edge, and confirms that the model id of the endpoint exists on the route. A route of the Messages surface lists no model ids, so the probe of that phase is the smallest message the surface takes, one token and streamed: its TTFB then holds the first event of the model as well as the edge, and each record names its probe |
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
- A surface reports what it reports. The Messages one carries no reasoning split, so
  `reasoning_tokens`, `content_tokens` and `tok_per_s_visible` have no value in a round of it:
  `report` names them as not reported, and `compare` names them when one side of its table holds a
  value and the other cannot.
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
- An endpoint is one surface of one service. The API of the vendor of the model answers on both of
  the surfaces that this tool speaks, at `/v1` and at `/anthropic`, and each takes an entry of its
  own; a table that ranges one of them says nothing about the other.
- A stream that carries no delta is a fault and not a fast answer, and a gateway that refuses one
  answers `200` or `403` with a JSON object where the stream should be. The tool reads the status of
  every streaming request, records such a request as an error with the status and a sample of the
  body on the record, and keeps it out of every median.
- A key that the process does not carry in its environment is a key that the tool cannot see: put
  it in the `.env` file beside the tool, whichever platform holds it, and `python bench.py list`
  says where it found it.
- A route can authenticate and list its models while it refuses every completion: OpenCode (Go) did
  that on 2026-09-29, `403 An active OpenCode Go subscription is required to use Go models`, with
  `/models` answering `200` all the while.
- Compare a rate in tokens, not in seconds, because two endpoints do not write the same number of
  tokens for the same prompt; and read a ratio against the other ratios of its own table, not
  against the absolute values of another run.

## License

MIT. See `LICENSE`.
