# The results of the campaigns

One directory holds one campaign. The name of the directory is the date and the host of the
campaign, as in `2026-09-23-macos`. Each directory holds one `summary.md` and the raw records
that the summary cites.

The time of a run matters, and it stays with the file. A file that `bench.py` writes names
the time of the run in three places: the name of the file (`<endpoint>_<UTC>.json`, and
`ab_<endpoint>_<UTC>.json` for a side of an A/B test), the field `meta.started_utc` inside,
and the header that the commands `report` and `compare` print.

| Directory | Host | Client | Records | Finding |
|---|---|---|---|---|
| `2026-09-23-macos/` | macOS 26.6.2 | `curl`, browser user agent | 110 | CommandCode is faster than OpenCode (Go) on every measurement |
| `2026-09-23-windows/` | Windows 11, Python 3.11.16 | `curl` 8.12.1, browser user agent | 96 | The same conclusion on another host and another network path |

Both campaigns measured the same model, `deepseek-v4.1-flash`, on the two routes CommandCode
and OpenCode (Go). Read the `summary.md` of a directory for the tables, the findings and the
limits of that campaign.

## 2026-09-23-macos

The first session. The scripts of the session wrote these files, so four of the five hold a
bare list of records without a `meta` block, and the time of the day of those four is not
recorded.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this campaign. |
| `commandcode_single_20260923.json` | 2026-09-23, time not recorded | The full characterization of CommandCode, with 55 records: transport, short answer, medium answer, streaming, prefill, 1 and 4 parallel requests, and the thinking toggle. |
| `ab_commandcode_20260923.json` | 2026-09-23, time not recorded | The A/B test, CommandCode side, with 18 records. |
| `ab_opencode-go_20260923.json` | 2026-09-23, time not recorded | The A/B test, OpenCode (Go) side, with 18 records. |
| `bench_py_example_commandcode_20260923T150937Z.json` | 2026-09-23T15:09:37Z | An example of the output of `bench.py run`, with 19 records. This file is the only one of the session that holds a `meta` block, and it names the host of the session: `jacanos-MacBook-Air.local`. |

## 2026-09-23-windows

The second session. Both files come from the same command, `bench.py ab`, and they carry the
same time: the two sides of one A/B test are written together.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this campaign. |
| `ab_commandcode_20260923T153444Z.json` | 2026-09-23T15:34:44Z | The A/B test, CommandCode side, with 48 records and the phases transport, short, long, prefill and concurrent. |
| `ab_opencode-go_20260923T153444Z.json` | 2026-09-23T15:34:44Z | The A/B test, OpenCode (Go) side, with 48 records and the same phases. |

## The format of a file

A file that `bench.py` writes holds two blocks:

```json
{"meta": {"endpoint": "commandcode", "model": "deepseek/deepseek-v4.1-flash",
          "phases": ["transport", "short", "long"], "started_utc": "20260923T153444Z",
          "host": "DESKTOP-08PBEHO", "platform": "Windows-10-...", "runner": "bench.py"},
 "records": [{"kind": "short", "iter": 1, "ttft_any_ms": 844.0, "out_tokens": 17, "...": "..."}]}
```

The `meta` block names the time in UTC, the host, the endpoint, the model and the phases. The
`records` block holds one object for each request, and the field `kind` names the phase that
made it. A record does not repeat the time, because every record of a file belongs to the one
run that the `meta` block names.

## How to read a file

Both commands print the time and the host of a file before the numbers, so a comparison of
two files always says which two runs it compares. A file without a `meta` block prints
`no meta block: the file records no time of the run`.

```bash
# the time, the median, the minimum and the maximum of one file
python3 bench.py report results/2026-09-23-windows/ab_opencode-go_20260923T153444Z.json

# one markdown table for the two sides of an A/B test
python3 bench.py compare results/2026-09-23-windows/ab_commandcode_20260923T153444Z.json \
                       results/2026-09-23-windows/ab_opencode-go_20260923T153444Z.json
```

## How to add a campaign

Give the new campaign its own directory, and point the run at it with `--out-dir`. The name
of each result file carries the time of the run by itself:

```bash
python3 bench.py ab --a commandcode --b opencode-go \
  --phases transport,short,long,prefill,thinking,concurrent --n 4 --concurrent 4 \
  --out-dir results/2026-09-24-macos
```

Two campaigns of the same day on the same host need two directories: add the time of the run
to the name of the second one, as in `2026-09-24T1012Z-macos`.

Then write the `summary.md` of the directory from the files, add one row to the table at the
top of this file, and add the generation time of each file to the table of its directory.
Keep the raw records of a campaign together with its summary: a table without its records
cannot be checked, and a record without its summary cannot be read.
