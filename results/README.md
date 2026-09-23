# The results of the campaigns

One directory holds one campaign. Each directory holds one `summary.md` and the raw records
that the summary cites.

The time of a run matters, and it stays with the directory and with the file. A run writes its
files into a directory that is named for the time of the run, as in `2026-09-23T161050Z`, so a
second run of the same day cannot mix with the first one. The name holds the time and nothing
else: the host and the operating system are in the table below, and in the `meta` block of
every file. Inside the directory, a file names the time of the run in three places: the name of
the file (`<endpoint>_<UTC>.json`, and `ab_<endpoint>_<UTC>.json` for a side of an A/B test),
the field `meta.started_utc`, and the header that the commands `report` and `compare` print.

| Directory | Host | Client | Records | Finding |
|---|---|---|---|---|
| `2026-09-23T150937Z/` | macOS 26.6.2 | `curl`, browser user agent | 102 | CommandCode is faster than OpenCode (Go) on every measurement |
| `2026-09-23T153444Z/` | Windows 11, Python 3.11.16 | `curl` 8.12.1, browser user agent | 96 | The same conclusion on another host and another network path |
| `2026-09-23T204204Z/` | Windows 11, Python 3.11.16 | `curl` 8.12.1, browser user agent | 108 | The same conclusion in a second window of the same host, four hours later |
| `2026-09-23T210256Z/` | Windows 11, Python 3.11.16 | `curl` 8.12.1, browser user agent | 108 | The same conclusion in a third window of that host, twenty minutes later |

The four campaigns measured the same model, `deepseek-v4.1-flash`, on the two routes CommandCode
and OpenCode (Go). Read the `summary.md` of a directory for the tables, the findings and the
limits of that campaign. The analysis of the campaigns with one another, and the limits that all
of them share, are in `../ANALYSIS.md`.

## 2026-09-23T150937Z

The first session. The scripts of the session wrote three of the four record files below, so
those three hold a bare list of records without a `meta` block, and the time of the day of those
three is not recorded. The directory takes its name from the only time that the session
recorded, 15:09:37Z, the time of the file that `bench.py` wrote.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this campaign. |
| `commandcode_20260923.json` | 2026-09-23, time not recorded | The full characterization of CommandCode, with 47 records: transport, short answer, medium answer, streaming, prefill, 1 and 4 parallel requests, and the thinking toggle. |
| `ab_commandcode_20260923.json` | 2026-09-23, time not recorded | The A/B test, CommandCode side, with 18 records. |
| `ab_opencode-go_20260923.json` | 2026-09-23, time not recorded | The A/B test, OpenCode (Go) side, with 18 records. |
| `commandcode_20260923T150937Z.json` | 2026-09-23T15:09:37Z | The output of `bench.py run` over transport, short, long, prefill and concurrent, with 19 records in the `{meta, records}` format. It is the only file of this campaign that holds a `meta` block, which names the host `jacanos-MacBook-Air.local`, and it is the only source of the row *TTFB of /models, reused connection* of `summary.md`, with its three requests over a ready socket. |

## 2026-09-23T153444Z

The second session. Both files come from the same command, `bench.py ab`, and they carry the
same time: the two sides of one A/B test are written together.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this campaign. |
| `ab_commandcode_20260923T153444Z.json` | 2026-09-23T15:34:44Z | The A/B test, CommandCode side, with 48 records and the phases transport, short, long, prefill and concurrent. |
| `ab_opencode-go_20260923T153444Z.json` | 2026-09-23T15:34:44Z | The A/B test, OpenCode (Go) side, with 48 records and the same phases. |

## 2026-09-23T204204Z

The third session, four hours after the second one on the same host. Both files come from the
same command, `bench.py ab`, and they carry the same time: the two sides of one A/B test are
written together. This campaign also ran the phase `thinking`, so each side holds 54 records
instead of 48.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this campaign. |
| `ab_commandcode_20260923T204204Z.json` | 2026-09-23T20:42:04Z | The A/B test, CommandCode side, with 54 records and the phases transport, short, long, prefill, thinking and concurrent. |
| `ab_opencode-go_20260923T204204Z.json` | 2026-09-23T20:42:04Z | The A/B test, OpenCode (Go) side, with 54 records and the same phases. |

## 2026-09-23T210256Z

The fourth session and the third one on this host, twenty minutes after the third campaign. Both
files come from the same command, `bench.py ab`, and they carry the same time: the two sides of
one A/B test are written together. Each side holds 54 records, with the same phases as the third
campaign.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this campaign. |
| `ab_commandcode_20260923T210256Z.json` | 2026-09-23T21:02:56Z | The A/B test, CommandCode side, with 54 records and the phases transport, short, long, prefill, thinking and concurrent. |
| `ab_opencode-go_20260923T210256Z.json` | 2026-09-23T21:02:56Z | The A/B test, OpenCode (Go) side, with 54 records and the same phases. |

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

## How to read a directory

Both commands print the time and the host of a file before the numbers, so a comparison of two
files always says which two runs it compares. A file without a `meta` block prints
`no meta block: the file records no time of the run`.

```bash
# each file of a campaign, with the time of each one
python3 bench.py report results/2026-09-23T153444Z

# the two sides of the last run in a directory
python3 bench.py compare results/2026-09-23T153444Z

# two files of your choice, in this order
python3 bench.py compare results/2026-09-23T150937Z/ab_commandcode_20260923.json \
                       results/2026-09-23T150937Z/ab_opencode-go_20260923.json
```

`compare` on a directory takes the newest file of each of the two endpoints that the directory
holds. Two runs of the same day in one directory are therefore no problem: the command compares
the newest pair, and it prints the time of each file, so the table says which run it holds. A
directory with more than two endpoints makes the command stop and name the tags that it found,
because the pair of an A/B test is then your choice and not a guess of the tool.

## How to add a campaign

A run makes its own directory, and the name of that directory carries the time of the run:

```bash
python3 bench.py ab --a commandcode --b opencode-go \
  --phases transport,short,long,prefill,thinking,concurrent --n 4 --concurrent 4
# -> results/2026-09-24T091533Z/ab_commandcode_20260924T091533Z.json
#    results/2026-09-24T091533Z/ab_opencode-go_20260924T091533Z.json
```

A campaign of more than one command takes one directory: give the same `--out-dir` to every
command of it, as in `--out-dir results/2026-09-24T091533Z`. The name of that directory
then holds the time of the first command of the campaign.

Then write the `summary.md` of the directory from the files, add one row to the table at the
top of this file, and add the generation time of each file to the table of its directory.
Keep the raw records of a campaign together with its summary: a table without its records
cannot be checked, and a record without its summary cannot be read.
