# model-canary

Every morning each model I pay for gets the same kind of coding task. The task's difficulty
never changes, so if the results change, the model or the plan changed. It answers three
questions:

- **Is it worse?** How much of the task did it get right?
- **Is it slower?** How long did the fix take?
- **Is it stingier?** How much of the plan's 5-hour and weekly limit did one run use?

Results are published on [btso.dev](https://btso.dev).

## The task

The model gets a small Python package, `tally`, and two jobs:

1. **Fix nine bugs.** Five modules (splitting money, merging time intervals, parsing
   durations, parsing `key=value` lines and billing time) must match their docstrings. The
   visible tests cover only part of that, and one bug only shows up when two modules work
   together.
2. **Build a scheduler from a spec.** `SCHEDULE.md` describes cron-style expressions: lists,
   ranges, steps, names, last-day and nth-weekday rules, shortcuts, how the day-of-month and
   day-of-week fields combine, a search horizon and a speed requirement. `schedule.py` starts
   as a stub.

`gen.py` writes a new variant every day from the date. The work stays the same size, but
names, rules and numbers change: which share gets a tied leftover cent, how halves round, the
separator and quote character, the duration units, whether day fields combine with OR or AND,
whether backwards ranges wrap, how far ahead to search and so on. A model can't pass by
remembering an earlier day, even though this repo is public.

After the run, 157 hidden tests the model never sees grade the work. Their answers come from
a reference implementation of the same variant, which `gen.py check` tests against answers
worked out by hand and against a brute-force search. The score is the share of hidden tests
passed. A run passes when the visible tests pass, every hidden test passes and the tests were
left alone. The unfixed code scores about 28 of 157.

Current models pass this almost every time. That's fine: a failure is the signal, and time,
tokens and cost on an identical piece of work are the trends to watch.

## How a run works

`run.py` generates the day's variant into a temporary git repo and runs the model through its
own CLI (Claude Code, Codex or OpenCode) with fixed settings: medium effort, no web access,
and none of my personal instructions, plugins or MCP servers. Three entries differ on effort:
Haiku 5.5 and Luna 6 also run a second time at high, as their own entries, and DeepSeek runs
at its default because OpenCode offers it low, high and max but no medium. It records:

- score, pass or fail, which hidden tests failed, and the diff
- wall-clock time
- tokens, and what they would cost at API list prices. Claude Code and OpenCode report that
  cost themselves. Codex reports only tokens, so `run.py` prices them at OpenAI's standard rates.
- the plan's 5-hour and weekly usage before and after the run

Both providers report usage in whole percents, and other work on the same account moves the
same numbers, so a single run's limit cost is rough. The trend over many runs is the useful
part. A run where the CLI itself failed (a limit, an outage) is marked `infra_error` and left
out of the summary. The task runs in `/tmp`, and the hidden tests are written only after the
model finishes. A run whose transcript shows the model reading this repo, the reference code
or the hidden tests is marked `harness_seen` and left out too. Runs that start or end past
100% of a limit are paid from credits and marked
`over_limit`, so they are left out of limit trends.

## Checking failures

Every failed run gets checked the same morning, with no step left to me. `review.py` runs after
the day's runs: for each miss it calls `regrade.py`, which rebuilds that day's task, applies the
run's saved diff and grades it again, so it shows whether the recorded result holds up, plus the
call and error behind each failed hidden test. A reviewer model (Opus 5.5) then reads those
against the spec and the model's code and writes a short note in `results/reviews.json` (code in
backticks), which the site shows next to the miss.

The reviewer can't take a run out of the results. If it thinks the task was at fault (a wrong
answer in the reference, a spec that says two things), or the regrade doesn't match the recorded
result, the note says so, the entry is marked `"cause": "unclear"` and the miss still counts.
Only an entry I mark `"cause": "harness"` myself, after fixing the task, is left out of the
summary. `python3 regrade.py DATE MODEL` checks a single run by hand.

## New versions and retired models

Each entry in `MODELS` in `run.py` is one line on the site, with its name, vendor and family.
When a vendor ships a new version, it gets its own entry next to the old one instead of taking
over the old one's history, so each line on the chart stays one model. The old entry gets
`until` (its last day) and `successor`: the two run side by side for two weeks, which gives the
site enough same-day pairs to say how the new version compares, and then the old one stops.
Entries are never deleted, so a retired model keeps its name and its full record on the site.

## When a day goes missing

A model whose CLI can't start (missing, logged out) is recorded as an infra error and the others
still run; the service then exits non-zero. Since the run happens on a home server, a check from
outside covers the rest: `.github/workflows/freshness.yml` reads `results/summary.json` every
morning after the run and opens an issue labelled `canary-down` when no run landed that day or an
active model has no result. It comments on the open issue while the problem lasts and closes it
once a full day lands.

## Results

Each run writes `results/runs/<date>/<model>/` (result, redacted transcript and diff) and
appends a line to `results/runs.jsonl`. `summarize.py` builds `results/summary.json` for the
site: per model its name, vendor, family, first and last day, retirement and every counted run,
plus the days a CLI version or plan changed, so the site can mark them instead of letting the
jump look like the model. Only the current task version counts, so if the task itself ever
changes, every model's history starts over.

## Running it

```bash
python3 run.py opus                      # one model, today's variant
python3 run.py all                       # every active model in run.py
python3 run.py --seed 2026-10-21 sol     # a specific day's variant
python3 summarize.py
```

`deploy/` has the daily script and the systemd user timer that runs it at 06:00.
