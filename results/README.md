# The results of the campaigns

One directory holds one campaign. The name of the directory is the date and the host of the
campaign, as in `2026-09-23-macos`. Each directory holds one `summary.md` and the raw records
that the summary cites.

| Directory | Host | Client | Records | Finding |
|---|---|---|---|---|
| `2026-09-23-macos/` | macOS 26.6.2 | `curl`, browser user agent | 110 | CommandCode is faster than OpenCode (Go) on every measurement |
| `2026-09-23-windows/` | Windows 11, Python 3.11.16 | `curl` 8.12.1, browser user agent | 96 | The same conclusion on another host and another network path |

Both campaigns measured the same model, `deepseek-v4.1-flash`, on the two routes
CommandCode and OpenCode (Go). Read the `summary.md` of a directory for the tables, the
findings and the limits of that campaign.

## The files of a campaign

Start with `summary.md`. The JSON files hold the raw records of one command, and every
measurement of a summary comes from one of them.

| Name | Content |
|---|---|
| `summary.md` | The tables, the findings and the limits of the campaign. |
| `ab_<endpoint>.json` | One side of the interleaved A/B test. The two files of a test are `ab_commandcode.json` and `ab_opencode-go.json`. |
| `<endpoint>_<UTC>.json` | The output of one single-endpoint run. The stamp of the time in UTC separates two runs of the same day. |
| `commandcode_single.json` | The first characterization session of the macOS campaign, with 55 records: transport, a short answer, a medium answer, streaming, prefill, 1 and 4 parallel requests, and the thinking toggle. |
| `bench_py_example_commandcode.json` | An example of the output of `bench.py run`, with 19 records. An example is useful to a reader who wants the shape of a record before a run. |

## The format of a file

A file that `bench.py` writes holds two blocks:

```json
{"meta": {"endpoint": "commandcode", "model": "deepseek/deepseek-v4.1-flash",
          "phases": ["transport", "short", "long"], "started_utc": "20260923T153444Z",
          "host": "DESKTOP-08PBEHO", "platform": "Windows-10-...", "runner": "bench.py"},
 "records": [{"kind": "short", "iter": 1, "ttft_any_ms": 844.0, "out_tokens": 17, "...": "..."}]}
```

The `meta` block names the endpoint, the model, the phases, the host and the time in UTC.
The `records` block holds one object for each request, and the field `kind` names the phase
that made it.

The four files of the first session (`commandcode_single.json`, the two files of the A/B
test, and the example) hold a bare list of records without the `meta` block. They come from
the scripts of that session, which are in the history of the repository.

## How to read a file

```bash
# the median, the minimum and the maximum of every measurement of one file
python3 bench.py report results/2026-09-23-macos/ab_opencode-go.json

# one markdown table for the two sides of an A/B test
python3 bench.py compare results/2026-09-23-windows/ab_commandcode.json \
                       results/2026-09-23-windows/ab_opencode-go.json
```

Both commands read a file of either format.

## How to add a campaign

Give the new campaign its own directory, and point the run at it with `--out-dir`:

```bash
python3 bench.py ab --a commandcode --b opencode-go \
  --phases transport,short,long,prefill,thinking,concurrent --n 4 --concurrent 4 \
  --out-dir results/2026-09-24-macos
```

Then write the `summary.md` of the directory from the two files, and add one row to the
table at the top of this file. Keep the raw records of a campaign together with its
summary: a table without its records cannot be checked, and a record without its summary
cannot be read.
