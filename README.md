# model-canary

Every morning each model I pay for gets the same small coding task. The task never changes,
so if the results change, the model or the plan changed. It answers three questions:

- **Is it worse?** Did it still fix every bug?
- **Is it slower?** How long did the same fix take?
- **Is it stingier?** How much of the plan's 5-hour and weekly limit did one run use?

Results are published on [btso.dev](https://btso.dev).

## The task

`task/` is a tiny Python package with three modules (`money`, `ranges`, `duration`) and a few
bugs. The model is told to make every function match its docstring. Its visible tests cover
only part of that, so a model that just makes the visible tests pass will miss some of it.

After the run, `hidden/test_hidden.py` (17 tests the model never sees) grades the fix. A run
passes when the visible tests pass, every hidden test passes and the tests were left alone.
The unfixed code scores 8 of 17.

## How a run works

`run.py` copies the task into a temporary git repo and runs the model through its own CLI
(Claude Code or Codex) with fixed settings: medium effort, no web access, and none of my
personal instructions, plugins or MCP servers. It records:

- pass or fail, hidden tests passed, and the diff
- wall-clock time
- tokens, and the API-price cost where the CLI reports it
- the plan's 5-hour and weekly usage before and after the run

Both providers report usage in whole percents, and other work on the same account moves the
same numbers, so a single run's limit cost is rough. The trend over many runs is the useful
part.

Each run writes `results/runs/<date>/<model>/` (result, redacted transcript and diff) and
appends a line to `results/runs.jsonl`. `summarize.py` builds `results/summary.json`.

## Running it

```bash
python3 run.py opus          # one model
python3 run.py all           # every model in run.py
python3 summarize.py
```

`deploy/` has the daily script and the systemd user timer that runs it at 06:00.
