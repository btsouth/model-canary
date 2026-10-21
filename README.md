# model-canary

Every morning each model I pay for gets the same kind of coding task. The task's difficulty
never changes, so if the results change, the model or the plan changed. It answers three
questions:

- **Is it worse?** How much of the task did it get right?
- **Is it slower?** How long did the fix take?
- **Is it stingier?** How much of the plan's 5-hour and weekly limit did one run use?

Results are published on [btso.dev](https://btso.dev).

## The task

The model gets a small Python package, `tally`, with five modules (splitting money, merging
time intervals, parsing durations, parsing `key=value` lines and billing time) and nine bugs.
It is told to make every function match its docstring. The visible tests cover only part of
that, so fixing just what the tests show isn't enough. One bug only shows up when two modules
work together.

`gen.py` writes a new variant every day from the date. The bugs and difficulty stay the same,
but names, rules and numbers change: which share gets a tied leftover cent, how halves round,
the field separator and quote character, the duration units, the currency and so on. A model
can't pass by remembering an earlier day, even though this repo is public.

After the run, 56 hidden tests the model never sees grade the fix. Their answers come from a
reference fix of the same variant. The score is the share of hidden tests passed. A run
passes when the visible tests pass, every hidden test passes and the tests were left alone.
The unfixed code scores about 28 of 56.

`python3 gen.py check 50` checks 50 variants: the reference fix must pass everything and the
unfixed code must fail the visible tests.

## How a run works

`run.py` generates the day's variant into a temporary git repo and runs the model through its
own CLI (Claude Code or Codex) with fixed settings: medium effort, no web access, and none of
my personal instructions, plugins or MCP servers. It records:

- score, pass or fail, which hidden tests failed, and the diff
- wall-clock time
- tokens, and the API-price cost where the CLI reports it
- the plan's 5-hour and weekly usage before and after the run

Both providers report usage in whole percents, and other work on the same account moves the
same numbers, so a single run's limit cost is rough. The trend over many runs is the useful
part. Runs that start or end past 100% of a limit are paid from credits and marked
`over_limit`, so they are left out of limit trends.

Each run writes `results/runs/<date>/<model>/` (result, redacted transcript and diff) and
appends a line to `results/runs.jsonl`. `summarize.py` builds `results/summary.json`.

## Running it

```bash
python3 run.py opus                      # one model, today's variant
python3 run.py all                       # every model in run.py
python3 run.py --seed 2026-10-21 sol     # a specific day's variant
python3 summarize.py
```

`deploy/` has the daily script and the systemd user timer that runs it at 06:00.
