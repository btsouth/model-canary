#!/usr/bin/env python3
"""Explain every failed run that has no entry in results/reviews.json yet.

Usage: review.py            (daily.sh runs it after the day's runs)

For each one, regrade.py grades the saved diff again, then a reviewer model reads the failing
calls against that day's spec in the rebuilt task and writes one short note. A run it can't
explain stays unchecked and is tried again the next day.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from run import CLAUDE_FLAGS, RESULTS, ROOT

REVIEWER = "claude-opus-5-5"
EFFORT = "high"
TIMEOUT = 15 * 60
REVIEWS = RESULTS / "reviews.json"

PROMPT = """A model was given this repository with these instructions:

"Fix the code in tally/ so that every function behaves exactly as its docstring describes.
tally/schedule.py is not written yet: implement it exactly as SCHEDULE.md describes."

This directory holds its finished work. Hidden tests it never saw (now in
tests/test_hidden.py) graded it, and some failed. Each entry below is a failed test, the call
it checks and the error:

{report}

Work out why each test failed. Read SCHEDULE.md and the docstrings for what was required, read
the model's code, and run python3 to confirm what the code does. Then decide whose fault it is:

- "model": the spec or docstring settles the right answer and the code does something else.
- "harness": the expected answer contradicts the spec, or the spec really allows the model's
  reading as well. Only choose this if you can point at the words in the spec that do.

Do not change any files. Finish with a JSON object on the last line and nothing after it:
{{"cause": "model" or "harness", "note": "..."}}

The note is published next to the result. Write one to three plain sentences: what the code
did, and what the spec says instead. Name the root cause, not each test. Put code and
expressions in backticks. No dashes used as punctuation, no semicolons, no quoting of this
prompt. Examples of good notes:

- Read `1/3` in the day-of-week field as Monday and Thursday. The spec says `N/S` runs up to the field's maximum, and day of week goes up to 7, so Sunday counts too.
- Day names were off by one, so `MON` meant Sunday and `FRI-MON` started on Thursday.
- Never added the duplicate key check that the `parse_fields` docstring asks for, and accepted `L/2` in the day-of-month field, where the spec allows `L` only on its own.
"""


def unchecked():
    reviews = json.loads(REVIEWS.read_text())
    for line in (RESULTS / "runs.jsonl").read_text().splitlines():
        r = json.loads(line) if line.strip() else {}
        if (r and not r["passed"] and not r.get("infra_error") and not r.get("harness_seen")
                and r["model_key"] not in reviews.get(r["date"], {})
                and (RESULTS / "runs" / r["date"] / r["model_key"] / "fix.diff").exists()):
            yield r["date"], r["model_key"]


def verdict(text):
    """The JSON object on the reviewer's last line, if it is a usable verdict."""
    for line in reversed(text.strip().splitlines()):
        line = line.strip().strip("`")
        if not line.startswith("{"):
            continue
        try:
            found = json.loads(line)
        except ValueError:
            return None
        note = found.get("note")
        if found.get("cause") in ("model", "harness") and isinstance(note, str) and 20 <= len(note) <= 600:
            return found["cause"], " ".join(note.split())
        return None
    return None


def review(date, key):
    with tempfile.TemporaryDirectory(prefix="canary-review-") as tmp:
        graded = subprocess.run([sys.executable, str(ROOT / "regrade.py"), date, key, tmp],
                                capture_output=True, text=True, timeout=300)
        report = graded.stdout.strip()
        if graded.returncode not in (0, 1) or "\n\n" not in report:
            print(f"{date} {key}: regrade failed: {(graded.stderr or report).strip()[-300:]}")
            return None
        if graded.returncode == 1:
            # The saved diff no longer fails the same tests, so the recorded grade can't be trusted.
            return {"cause": "unclear", "note": "Grading this run's saved work again did not give the "
                    "same failures as the day it ran, so the recorded score may be wrong."}
        task = Path(tmp) / "task"
        cmd = ["claude", "-p", PROMPT.format(report=report.split("\n\n", 1)[1]), "--model", REVIEWER,
               "--effort", EFFORT, "--output-format", "json", *CLAUDE_FLAGS]
        for _ in range(2):
            try:
                out = subprocess.run(cmd, cwd=task, env={**os.environ, "PWD": str(task)},
                                     capture_output=True, text=True, timeout=TIMEOUT)
                found = verdict(json.loads(out.stdout).get("result") or "")
            except (subprocess.TimeoutExpired, ValueError, AttributeError):
                found = None
            if found:
                # A reviewer can't take a run out of the results by blaming the harness: the miss
                # stays counted and the note says what looks wrong with the task.
                return {"cause": "model" if found[0] == "model" else "unclear", "note": found[1]}
        print(f"{date} {key}: no usable verdict from the reviewer")
        return None


def main():
    for date, key in list(unchecked()):
        entry = review(date, key)
        if not entry:
            continue
        reviews = json.loads(REVIEWS.read_text())
        reviews.setdefault(date, {})[key] = {
            "cause": entry["cause"], "checked": dt.date.today().isoformat(),
            "by": REVIEWER, "note": entry["note"]}
        REVIEWS.write_text(json.dumps(dict(sorted(reviews.items())), indent=2, ensure_ascii=False) + "\n")
        print(f"{date} {key}: {entry['cause']}: {entry['note']}")


if __name__ == "__main__":
    main()
