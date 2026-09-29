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
surfaces, and two gateways that resell it, CommandCode under two model ids and OpenCode (Go). Ten
rounds measured them on one Windows 11 host.

### The newest results of every endpoint

<!-- latest:begin -->
| Endpoint | Surface | Round (UTC) | Short: TTFT visible | Long: TTFT visible | Long: total | Long: decode | Long: visible | 4 parallel: one | 4 parallel: total | Long: output tokens | TTFB, ready socket |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `deepseek-official` | openai-completions | 2026-09-29 11:58Z | 801.6 ms | 1581.3 ms | 2648.4 ms | 367.6 tokens/s | 442.7 tokens/s | 368.2 tokens/s | 930.8 tokens/s | 635 | 253.3 ms |
| `deepseek-official-messages` | anthropic-messages | 2026-09-29 07:45Z | 820.2 ms | 1284.4 ms | 2422.6 ms | 356.5 tokens/s | - | 361.8 tokens/s | 672.9 tokens/s | 642 | 289.7 ms |
| `commandcode-fast` | openai-completions | 2026-09-29 11:58Z | 1110.7 ms | 1343.7 ms | 2500.4 ms | 370.1 tokens/s | 446.6 tokens/s | 361.4 tokens/s | 808.6 tokens/s | 590 | 15.9 ms |
| `commandcode` | openai-completions | 2026-09-29 11:58Z | 1851.4 ms | 3718.2 ms | 5647.6 ms | 217.8 tokens/s | 247.9 tokens/s | 206.2 tokens/s | 447.4 tokens/s | 896 | 16.4 ms |
| `opencode-go` | openai-completions | 2026-09-23 21:23Z | 1913.3 ms | 2043.5 ms | 4006.4 ms | 260.3 tokens/s | 291.9 tokens/s | 243.6 tokens/s | 423.9 tokens/s | 569 | 296.8 ms |

5 endpoints across 3 rounds under `results/`, fastest short answer first. Each row comes from the newest file that measures that endpoint, and the newest round of the tree is 2026-09-29 11:58Z; a row names its own round, so two rows of this table can come from two rounds and the absolute values of two rounds are not directly comparable (`ANALYSIS.md` states that limit). `Long: output tokens` is the median work of that phase: read a rate beside it, and prefer the rate of the visible content when the work of two rows differs by more than a fifth. `TTFB, ready socket` is the per-request cost of the edge, the row that separates the two halves of a route.
<!-- latest:end -->

That table is written by the tool and not by hand: `python bench.py latest --write README.md` reads
the newest result file of each endpoint under `results/` and fills in what stands between those two
markers, leaving every other line of this file alone. The numbers of this page are therefore one
command away from the records that back them.

### What the four comparisons found

- **CommandCode against OpenCode (Go)**, four rounds on 2026-09-23, twenty minutes to four hours
  apart. CommandCode is faster on every measurement of every round: the gateway of OpenCode adds 250
  to 325 ms to each request with a ready socket, nine to twenty times the cost of CommandCode, and
  OpenCode decodes about 1.6 times slower in the steady state.
- **The vendor route against CommandCode**, one interleaved round on 2026-09-29. CommandCode wins
  every row of the transport, 16.4 ms against 253.3 ms for a request on a ready socket, and the
  vendor route wins every row of the model: a short answer at 0.72 s of TTFT against 1.78 s, and a
  sustained decode of 367.6 tokens/s against 217.8. The edge of the vendor route is expensive and
  its model is fast; the gateway of CommandCode is the other way round, so a route is not faster
  than another without naming the half of it that you pay for.
- **The two surfaces of the vendor service against each other**, one interleaved round on
  2026-09-29. Every row of a phase of the model comes out `same` within 10 percent — a short answer
  at 673.6 against 695.4 ms and a sustained decode of 367.2 against 356.5 tokens/s — so the surface a
  client speaks does not change what the model costs. What it changes is what a client can read: the
  Messages surface reports no reasoning split, and three rows of its side of the table have no value
  at all.
- **The two model ids of CommandCode and the vendor, in one session of three**, on 2026-09-29. The
  fast tier of the reseller beats its normal tier by 1.70 to 1.81 times on the rates and 1.67 to 2.78
  times on the delays — a short answer at 0.94 s against 1.78 s — and then lands on the vendor of the
  model: every rate comes out `same`, 370.1 against 367.6 tokens/s sustained, and only the short
  answer separates them, 939.4 against 715.0 ms. The fast tier is the one endpoint of this table that
  holds both halves of a route, the cheap edge of the reseller and the decode of the vendor.

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
| `commandcode-fast` | `openai-completions` | `https://api.commandcode.ai/provider/v1` | `deepseek/deepseek-v4.1-flash-fast` | `COMMANDCODE_API_KEY` |
| `opencode-go` | `openai-completions` | `https://opencode.ai/zen/go/v1` | `deepseek-v4.1-flash` | `OPENCODE_GO_API_KEY`, or `OPENCODE_API_KEY` |
| `deepseek-official` | `openai-completions` | `https://api.deepseek.com/v1` | `deepseek-flash` | `DEEPSEEK_API_KEY` |
| `deepseek-official-messages` | `anthropic-messages` | `https://api.deepseek.com/anthropic` | `deepseek-flash` | `DEEPSEEK_API_KEY` |

`opencode-go` also requires the header `x-opencode-session`. The first two rows are two tiers of one
reseller on one base URL: the same service under two model ids, which the catalog prices
differently. The last two rows are the two surfaces of one service, the API of the vendor of the
model that the gateways resell: `/v1` is its OpenAI-compatible path and `/anthropic` its Messages
path. An endpoint takes **one** surface and one model, so a service of two takes two entries, and
the tool can then put the two of them against each other as readily as two providers.

`python bench.py list` prints this table and says whether each key resolves and where it found it. A
route other than these five takes one entry in `ENDPOINTS` at the top of `bench.py`:

```python
"example": {"base_url": "https://api.example.com/v1", "model": "vendor/model-id",
            "api": OPENAI,  # or MESSAGES for a surface of the shape of POST /v1/messages
            "key_env": "EXAMPLE_API_KEY", "key_env_alt": ["EXAMPLE_KEY"], "session_header": False},
```

## How to run it

```bash
python bench.py list                                           # the endpoints, their surfaces and their keys
python bench.py ab --a commandcode --b opencode-go --n 4       # the A/B test, all four phases
python bench.py ab --a commandcode --b deepseek-official --c commandcode-fast   # a round of three
python bench.py ab --a deepseek-official --b deepseek-official-messages   # the two surfaces of one service
python bench.py run --endpoint deepseek-official-messages      # one surface on its own
python bench.py report results/2026-09-23T210256Z              # one file, or every file of a directory
python bench.py compare results/2026-09-23T210256Z             # the two sides of the last run in it
python bench.py latest                                         # one table of the newest results
python bench.py latest --by decode --write README.md           # ... and fill it into the document
python bench.py compare results/2026-09-29T064339Z/ab_commandcode_20260929T064339Z.json \
                       results/2026-09-29T064339Z/ab_deepseek-official_20260929T064339Z.json
```

`ab` alternates the endpoints, so the load of the provider hits every side in the same way, and `--n`
is the number of rounds of the `short` and `long` phases (5 and 4 requests each). A third endpoint
goes in `--c`, and the three are interleaved inside every round: `compare` then takes any two of the
three files that the command writes, so one round of three holds three comparisons of a single
session instead of a quotient read through a fourth route. It prints one line for each request as it
arrives. Files land in a new directory named for the time of the run in UTC,
`results/<date>T<time>Z/`, so a second run of the same day cannot mix with the first one;
`--out-dir` puts the files of several commands in one directory of a round. `run --endpoint NAME`
measures one route on its own.

`latest` reads the whole `results/` tree and prints **one table of the newest results of every
endpoint**: one line per endpoint, taken from the newest file that measures it, fastest short answer
first (or `--by long`, `total`, `decode`, `visible`). Every line names its own round, because two
lines of that table can come from two rounds. With `--write FILE` the command fills that table into
the file between the markers `<!-- latest:begin -->` and `<!-- latest:end -->` and touches nothing
else, which is how the table in the Results section of this file is kept from going stale: it is one
command away from the records and no line of it is hand-kept.

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
