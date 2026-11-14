#!/usr/bin/env python3
"""Check a saved run's grade by grading its saved diff again from scratch.

Usage: regrade.py DATE MODEL [DIR]

Rebuilds the day's task from the run's seed, applies the run's fix.diff, runs the visible and
hidden tests and compares the result with the recorded one. For each hidden test that fails it
prints the test and its error, which is what review.py reads to explain the miss. With DIR,
the rebuilt task (fix applied, hidden tests in tests/test_hidden.py) is left there.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import gen
from run import RESULTS, grade, sh


def main(date, key, keep=None):
    folder = RESULTS / "runs" / date / key
    record = json.loads((folder / "result.json").read_text())
    if record.get("task_version") != gen.VERSION:
        sys.exit(f"Run used task version {record.get('task_version')}, gen.py is version {gen.VERSION}.")
    with tempfile.TemporaryDirectory(prefix="canary-regrade-") as tmp:
        tmp = keep or tmp
        gen.generate(record["seed"], tmp)
        task, hidden = Path(tmp) / "task", Path(tmp) / "hidden.py"
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.name=canary", "-c", "user.email=canary@localhost", "commit", "-qm", "task"]):
            sh(*cmd, cwd=task)
        if (folder / "fix.diff").read_text().strip():
            applied = sh("git", "apply", str(folder / "fix.diff"), cwd=task)
            if applied.returncode:
                sys.exit(f"fix.diff does not apply: {applied.stderr.strip()}")
        _, grades = grade(task, hidden)
        same = sorted(grades["hidden_failed"]) == sorted(record["hidden_failed"])
        print(f"{date} {key}: recorded {record['hidden_passed']}/{record['hidden_total']}, "
              f"regraded {grades['hidden_passed']}/{grades['hidden_total']}, "
              f"{'same failures' if same else 'DIFFERENT failures'}")
        if not same:
            print(f"  recorded: {record['hidden_failed']}\n  regraded: {grades['hidden_failed']}")
        # Show why each hidden test failed.
        (task / "tests" / "test_hidden.py").write_text(hidden.read_text())
        sys.path.insert(0, str(task))
        suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_hidden")
        result = unittest.TestResult()
        suite.run(result)
        lines = hidden.read_text().splitlines()
        # The checked call is the line after the def, or after `with self.assertRaises(...)`.
        body = {l.strip()[9:].split("(")[0]: lines[i + 2 if lines[i + 1].strip().startswith("with ") else i + 1].strip()
                for i, l in enumerate(lines) if l.strip().startswith("def test_")}
        for test, trace in sorted(result.failures + result.errors, key=lambda f: f[0].id()):
            name = test.id().split(".")[-1][5:]
            print(f"\n{name}\n  {body.get(name, '')}\n  {trace.strip().splitlines()[-1]}")
    return 0 if same else 1


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
