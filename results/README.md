# The results of the rounds

One directory holds one round. Each directory holds one `summary.md` and the raw records
that the summary cites.

The time of a run matters, and it stays with the directory and with the file. A run writes its
files into a directory that is named for the time of the run, as in `2026-09-23T161050Z`, so a
second run of the same day cannot mix with the first one. The name holds the time and nothing
else: the host is in the table below, and in the `meta` block of every file. Inside the directory,
a file names the time of the run in three places: the name of
the file (`<endpoint>_<UTC>.json`, and `ab_<endpoint>_<UTC>.json` for a side of an A/B test),
the field `meta.started_utc`, and the header that the commands `report` and `compare` print.

| Directory | Host | Records | Finding |
|---|---|---|---|
| `2026-09-23T153444Z/` | Windows 11 | 94 | CommandCode is faster than OpenCode (Go) on every measurement |
| `2026-09-23T204204Z/` | Windows 11 | 96 | The same conclusion in a second round of the same host, four hours later |
| `2026-09-23T210256Z/` | Windows 11 | 96 | The same conclusion in a third round of that host, twenty minutes later |
| `2026-09-23T212350Z/` | Windows 11 | 96 | The same conclusion in a fourth round of that host, twenty-one minutes later |

The four rounds measured the same model, `deepseek-v4.1-flash`, on the two routes CommandCode
and OpenCode (Go), on one host. Read the `summary.md` of a directory for the tables, the findings
and the limits of that round. The comparison of the rounds with one another, and the limits that
all of them share, are in `../ANALYSIS.md`.

A session before these wrote records with an older version of the tool: a phase vocabulary
of its own, no `meta` block in three of its four files, and a row of its table whose other side
was never recorded. Those records are removed from the tree, because a round that a reader
cannot check is worse than no round; they remain in the history of this repository.

## 2026-09-23T153444Z

The first round on this host, and the first run of the tool in its present form. Both files
come from the same command, `bench.py ab`, and they carry the same time: the two sides of one A/B
test are written together.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this round. |
| `ab_commandcode_20260923T153444Z.json` | 2026-09-23T15:34:44Z | The A/B test, CommandCode side, with 47 records and the phases transport, short, long and concurrent. |
| `ab_opencode-go_20260923T153444Z.json` | 2026-09-23T15:34:44Z | The A/B test, OpenCode (Go) side, with 47 records and the same phases. |

## 2026-09-23T204204Z

The second round, four hours after the first one on the same host. Both files come from the same
command, `bench.py ab`, and they carry the same time: the two sides of one A/B test are written
together.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this round. |
| `ab_commandcode_20260923T204204Z.json` | 2026-09-23T20:42:04Z | The A/B test, CommandCode side, with 48 records and the phases transport, short, long and concurrent. |
| `ab_opencode-go_20260923T204204Z.json` | 2026-09-23T20:42:04Z | The A/B test, OpenCode (Go) side, with 48 records and the same phases. |

## 2026-09-23T210256Z

The third round, twenty minutes after the second one. Both files come from the same command,
`bench.py ab`, and they carry the same time: the two sides of one A/B test are written together.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this round. |
| `ab_commandcode_20260923T210256Z.json` | 2026-09-23T21:02:56Z | The A/B test, CommandCode side, with 48 records and the phases transport, short, long and concurrent. |
| `ab_opencode-go_20260923T210256Z.json` | 2026-09-23T21:02:56Z | The A/B test, OpenCode (Go) side, with 48 records and the same phases. |

## 2026-09-23T212350Z

The fourth round, twenty-one minutes after the third one. Both files come from the same command,
`bench.py ab`, and they carry the same time: the two sides of one A/B test are written together.

| File | Generated (UTC) | Content |
|---|---|---|
| `summary.md` | - | The tables, the findings and the limits of this round. |
| `ab_commandcode_20260923T212350Z.json` | 2026-09-23T21:23:50Z | The A/B test, CommandCode side, with 48 records and the phases transport, short, long and concurrent. |
| `ab_opencode-go_20260923T212350Z.json` | 2026-09-23T21:23:50Z | The A/B test, OpenCode (Go) side, with 48 records and the same phases. |

## The format of a file

A file that `bench.py` writes holds two blocks:

```json
{"meta": {"endpoint": "commandcode", "model": "deepseek/deepseek-v4.1-flash",
          "phases": ["transport", "short", "long", "concurrent"],
          "started_utc": "20260923T210256Z", "host": "DESKTOP-08PBEHO", "runner": "bench.py"},
 "records": [{"kind": "short", "iter": 1, "ttft_any_ms": 826.3, "out_tokens": 17, "...": "..."}]}
```

The `meta` block names the time in UTC, the host, the endpoint, the model and the phases. The
`records` block holds one object for each request, and the field `kind` names the phase that
made it. A record does not repeat the time, because every record of a file belongs to the one
run that the `meta` block names. A file written by an earlier version of the tool may hold more
fields.

## How to read a directory

Both commands print the time and the host of a file before the numbers, so a comparison of two
files always says which two runs it compares.

```bash
# each file of a round, with the time of each one
python bench.py report results/2026-09-23T153444Z

# the two sides of the last run in a directory
python bench.py compare results/2026-09-23T153444Z

# two files of your choice, in this order
python bench.py compare results/2026-09-23T153444Z/ab_commandcode_20260923T153444Z.json \
                       results/2026-09-23T153444Z/ab_opencode-go_20260923T153444Z.json
```

`compare` on a directory takes the newest file of each of the two endpoints that the directory
holds. Two runs of the same day in one directory are therefore no problem: the command compares
the newest pair, and it prints the time of each file, so the table says which run it holds. A
directory with more than two endpoints makes the command stop and name the tags that it found,
because the pair of an A/B test is then your choice and not a guess of the tool.

## How to add a round

A run makes its own directory, and the name of that directory carries the time of the run:

```bash
python bench.py ab --a commandcode --b opencode-go --n 4
# -> results/2026-09-24T091533Z/ab_commandcode_20260924T091533Z.json
#    results/2026-09-24T091533Z/ab_opencode-go_20260924T091533Z.json
```

The command with no `--phases` runs all four phases. A round of more than one command takes one
directory: give the same `--out-dir` to every command of it, as in
`--out-dir results/2026-09-24T091533Z`. The name of that directory then holds the time of the first
command of the round.

Then write the `summary.md` of the directory from the files, add one row to the table at the
top of this file, and add the generation time of each file to the table of its directory.
Keep the raw records of a round together with its summary: a table without its records
cannot be checked, and a record without its summary cannot be read.
