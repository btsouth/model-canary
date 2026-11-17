#!/usr/bin/env python3
"""Run the canary task once for one model and append the result to results/runs.jsonl.

Usage: run.py [--seed SEED] MODEL [MODEL ...]   (keys from MODELS below, or "all")

The seed picks the day's task variant (see gen.py) and defaults to today's date, so every
model gets the same variant on the same day.
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import gen

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
TIMEOUT = 20 * 60
EFFORT = "medium"


def effort_of(spec):
    """Claude Code and Codex run at EFFORT unless the model's entry names another. OpenCode
    runs at the model's own default: DeepSeek has low, high and max, but no medium."""
    return "default" if spec["harness"] == "opencode" else spec.get("effort", EFFORT)

# Each entry is one line on the site. `label`, `vendor` and `family` name and group it there;
# `base` marks a second effort level of another entry. When a new version replaces a model, the
# new one is added next to it and the old one gets `until` (its last day) and `successor`: they
# run side by side for two weeks, then the old one stops. Entries are never deleted, so a
# retired model keeps its name and its record on the site.
MODELS = {
    "opus": {"harness": "claude", "model": "claude-opus-5-5", "plan": "Claude Ultra",
             "label": "Opus 5.5", "vendor": "Anthropic", "family": "opus"},
    "fable52": {"harness": "claude", "model": "claude-fable-5-2", "plan": "Claude Ultra",
                "label": "Fable 5.2", "vendor": "Anthropic", "family": "fable"},
    "fable": {"harness": "claude", "model": "claude-fable-5-1", "plan": "Claude Ultra",
              "label": "Fable 5.1", "vendor": "Anthropic", "family": "fable",
              "until": "2026-11-26", "successor": "fable52"},
    "sonnet": {"harness": "claude", "model": "claude-sonnet-5-5", "plan": "Claude Ultra",
               "label": "Sonnet 5.5", "vendor": "Anthropic", "family": "sonnet"},
    "haiku": {"harness": "claude", "model": "claude-haiku-5-5", "plan": "Claude Ultra",
              "label": "Haiku 5.5", "vendor": "Anthropic", "family": "haiku"},
    "haiku-high": {"harness": "claude", "model": "claude-haiku-5-5", "plan": "Claude Ultra", "effort": "high",
                   "label": "Haiku 5.5", "vendor": "Anthropic", "family": "haiku", "base": "haiku"},
    "sol62": {"harness": "codex", "model": "gpt-6.2-sol", "plan": "ChatGPT",
              "label": "Sol 6.2", "vendor": "OpenAI", "family": "sol"},
    "sol": {"harness": "codex", "model": "gpt-6.1-sol", "plan": "ChatGPT",
            "label": "Sol 6.1", "vendor": "OpenAI", "family": "sol",
            "until": "2026-11-30", "successor": "sol62"},
    "terra": {"harness": "codex", "model": "gpt-6.1-terra", "plan": "ChatGPT",
              "label": "Terra 6.1", "vendor": "OpenAI", "family": "terra"},
    "astra62": {"harness": "codex", "model": "gpt-6.2-astra", "plan": "ChatGPT",
                "label": "Astra 6.2", "vendor": "OpenAI", "family": "astra"},
    "astra": {"harness": "codex", "model": "gpt-6-astra", "plan": "ChatGPT",
              "label": "Astra 6", "vendor": "OpenAI", "family": "astra",
              "until": "2026-11-30", "successor": "astra62"},
    "luna": {"harness": "codex", "model": "gpt-6-luna", "plan": "ChatGPT",
             "label": "Luna 6", "vendor": "OpenAI", "family": "luna"},
    "luna-high": {"harness": "codex", "model": "gpt-6-luna", "plan": "ChatGPT", "effort": "high",
                  "label": "Luna 6", "vendor": "OpenAI", "family": "luna", "base": "luna"},
    "deepseek": {"harness": "opencode", "model": "opencode-go/deepseek-v4.1-flash", "plan": "OpenCode Go",
                 "label": "DeepSeek V4.1 Flash", "vendor": "DeepSeek", "family": "deepseek"},
}


def active(key, date):
    """Whether a model still runs on this date (an ISO day)."""
    until = MODELS[key].get("until")
    return until is None or date <= until


# Codex reports tokens but no price, so its runs are priced here: OpenAI's standard API list
# price per 1M tokens (input, cached input, output) for prompts up to 272K tokens, from
# https://developers.openai.com/api/docs/pricing on 2026-10-31 (the 6.2 models on 2026-11-17).
# A run keeps the price it was recorded with. Codex's output count already includes reasoning
# tokens.
OPENAI_PRICES = {
    "gpt-6.2-astra": (8.00, 0.40, 40.00),
    "gpt-6.2-sol": (2.00, 0.10, 10.00),
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
}


def openai_cost(model, tokens):
    if model not in OPENAI_PRICES:
        return None
    price_in, price_cached, price_out = OPENAI_PRICES[model]
    return round((tokens["input"] * price_in + tokens["cache_read"] * price_cached
                  + tokens["output"] * price_out) / 1e6, 6)


PROMPT = (
    "This repository has bugs and its tests in tests/ fail. Fix the code in tally/ so that "
    "every function behaves exactly as its docstring describes. tally/schedule.py is not "
    "written yet: implement it exactly as SCHEDULE.md describes. The tests only cover part of "
    "the required behaviour, so read the docstrings and SCHEDULE.md carefully. Do not change "
    "the tests, the docstrings or SCHEDULE.md. Run the tests with `python3 -m unittest`. "
    "Stop when you are done."
)

# Codex reads ~/.codex/AGENTS.md even with --ignore-user-config, so it runs from its own
# home that shares only the login.
CODEX_HOME = Path.home() / ".codex-canary"
CODEX_AUTH = Path.home() / ".codex" / "auth.json"

# OpenCode 2 runs from its own home too, so it sees none of my config or instructions. Its
# only setting points the Go provider at a key file.
OPENCODE = Path.home() / ".local" / "opt" / "opencode2" / "bin" / "opencode"
OPENCODE_HOME = Path.home() / ".opencode-canary"
GO_KEY = Path.home() / ".config" / "model-canary" / "opencode-go.key"

CLAUDE_FLAGS = [
    "--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands",
    "--no-session-persistence", "--permission-mode", "bypassPermissions",
    "--disallowed-tools", "WebFetch,WebSearch,Task,Workflow",
]


def sh(*cmd, cwd=None, env=None, timeout=None):
    return subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, capture_output=True, text=True)


def secrets():
    """Token values that must never reach a committed file."""
    found = set()
    try:
        found.add(GO_KEY.read_text().strip())
    except OSError:
        pass
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        found.add(os.environ["CLAUDE_CODE_OAUTH_TOKEN"])
    for path in (Path.home() / ".claude" / ".credentials.json", CODEX_AUTH):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, str) and len(item) >= 20:
                found.add(item)
    return found


TOKEN_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
]


def redact(text, values):
    for value in values:
        text = text.replace(value, "[redacted]")
    for pattern in TOKEN_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def claude_limits(cwd):
    """Read the Claude plan's 5-hour and weekly usage with a one-word Haiku call."""
    out = sh("claude", "-p", "Reply with ok.", "--model", "claude-haiku-5-5",
             "--output-format", "stream-json", "--verbose", *CLAUDE_FLAGS, cwd=cwd, timeout=120)
    for line in out.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "rate_limit_event":
            windows = event["rate_limit_info"].get("unifiedWindows", {})
            return {name: windows.get(name, {}).get("utilization") for name in ("five_hour", "seven_day")}
    return None


def run_claude(spec, workdir):
    cmd = ["claude", "-p", PROMPT, "--model", spec["model"], "--effort", effort_of(spec),
           "--output-format", "stream-json", "--verbose", *CLAUDE_FLAGS]
    before = claude_limits(workdir)
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=workdir, env={**os.environ, "PWD": str(workdir)},
                              capture_output=True, text=True, timeout=TIMEOUT)
        stdout, code, timed_out = proc.stdout, proc.returncode, False
    except subprocess.TimeoutExpired as err:
        stdout, code, timed_out = (err.stdout or b"").decode() if isinstance(err.stdout, bytes) else (err.stdout or ""), None, True
    wall = time.monotonic() - started
    after = claude_limits(workdir)
    usage, cost, turns = {}, None, None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            u = event.get("usage", {})
            usage = {
                "input": u.get("input_tokens", 0),
                "cache_read": u.get("cache_read_input_tokens", 0),
                "cache_write": u.get("cache_creation_input_tokens", 0),
                "output": u.get("output_tokens", 0),
                "reasoning": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
            }
            cost, turns = event.get("total_cost_usd"), event.get("num_turns")
    version = sh("claude", "--version").stdout.strip()
    return stdout, {"exit_code": code, "timed_out": timed_out, "wall_seconds": round(wall, 1),
                    "tokens": usage, "api_cost_usd": cost, "turns": turns,
                    "limits": {"before": before, "after": after}, "harness_version": version}


def codex_home():
    CODEX_HOME.mkdir(exist_ok=True)
    link = CODEX_HOME / "auth.json"
    if link.exists() and not link.is_symlink():
        # Codex refreshed the login by rewriting the file; keep the newer one for both homes.
        if link.stat().st_mtime > CODEX_AUTH.stat().st_mtime:
            shutil.copy2(link, CODEX_AUTH)
        link.unlink()
    if not link.exists():
        link.symlink_to(CODEX_AUTH)


def run_codex(spec, workdir):
    codex_home()
    env = {**os.environ, "CODEX_HOME": str(CODEX_HOME), "PWD": str(workdir)}
    cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "--ignore-rules",
           "-m", spec["model"], "-c", f'model_reasoning_effort="{effort_of(spec)}"',
           # The bwrap sandbox can't start on the devbox. Like the Claude run, it works in a
           # throwaway temp repo instead.
           "--dangerously-bypass-approvals-and-sandbox", PROMPT]
    marker = time.time()
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True,
                              timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        stdout, code, timed_out = proc.stdout, proc.returncode, False
    except subprocess.TimeoutExpired as err:
        stdout, code, timed_out = (err.stdout or b"").decode() if isinstance(err.stdout, bytes) else (err.stdout or ""), None, True
    wall = time.monotonic() - started
    codex_home()
    usage = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "reasoning": 0}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "turn.completed":
            u = event.get("usage", {})
            usage["input"] += u.get("input_tokens", 0) - u.get("cached_input_tokens", 0)
            usage["cache_read"] += u.get("cached_input_tokens", 0)
            usage["cache_write"] += u.get("cache_write_input_tokens", 0)
            usage["output"] += u.get("output_tokens", 0)
            usage["reasoning"] += u.get("reasoning_output_tokens", 0)
    limits = {"before": None, "after": None}
    sessions = sorted((p for p in (CODEX_HOME / "sessions").rglob("*.jsonl") if p.stat().st_mtime >= marker),
                      key=lambda p: p.stat().st_mtime)
    readings = []
    for path in sessions[-1:]:
        for line in path.read_text().splitlines():
            try:
                payload = json.loads(line).get("payload", {})
            except ValueError:
                continue
            rl = payload.get("rate_limits") if isinstance(payload, dict) else None
            if rl:
                readings.append({"five_hour": (rl.get("primary") or {}).get("used_percent"),
                                 "seven_day": (rl.get("secondary") or {}).get("used_percent")})
    if readings:
        to_frac = lambda r: {k: (v / 100 if v is not None else None) for k, v in r.items()}
        limits = {"before": to_frac(readings[0]), "after": to_frac(readings[-1])}
    version = sh("codex", "--version").stdout.strip()
    return stdout, {"exit_code": code, "timed_out": timed_out, "wall_seconds": round(wall, 1),
                    "tokens": usage, "api_cost_usd": openai_cost(spec["model"], usage), "turns": None,
                    "limits": limits, "harness_version": version}


def go_limits():
    """Read the OpenCode Go plan's 5-hour and weekly usage from its usage API."""
    import urllib.request
    try:
        request = urllib.request.Request("https://opencode.ai/zen/go/v1/usage", headers={
            "Authorization": "Bearer " + GO_KEY.read_text().strip(), "User-Agent": "model-canary/1"})
        with urllib.request.urlopen(request, timeout=15) as response:
            usage = json.load(response)["usage"]
        pct = lambda name: usage[name]["percent"] / 100 if isinstance(usage.get(name), dict) else None
        return {"five_hour": pct("rolling"), "seven_day": pct("weekly"), "monthly": pct("monthly")}
    except Exception:
        return None


def run_opencode(spec, workdir):
    import sqlite3
    # OpenCode takes its project folder from $PWD, not the real working directory.
    env = {**os.environ, "HOME": str(OPENCODE_HOME), "OPENCODE_DISABLE_CLAUDE_CODE": "1", "PWD": str(workdir)}
    cmd = [str(OPENCODE), "run", "--standalone", "--format", "json", "--auto", "-m", spec["model"], PROMPT]
    before = go_limits()
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True,
                              timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        stdout, code, timed_out = proc.stdout, proc.returncode, False
    except subprocess.TimeoutExpired as err:
        stdout, code, timed_out = (err.stdout or b"").decode() if isinstance(err.stdout, bytes) else (err.stdout or ""), None, True
    wall = time.monotonic() - started
    after = go_limits()
    sessions = set()
    for line in stdout.splitlines():
        try:
            sessions.add(json.loads(line)["sessionID"])
        except (ValueError, KeyError, TypeError):
            pass
    # OpenCode's JSON output has no token counts; they live in its database.
    usage = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "reasoning": 0}
    cost, turns = 0.0, 0
    db = OPENCODE_HOME / ".local" / "share" / "opencode" / "opencode.db"
    if sessions and db.exists():
        conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=5)
        marks = ",".join("?" * len(sessions))
        for (data,) in conn.execute(f"SELECT data FROM session_message WHERE type='assistant' AND session_id IN ({marks})",
                                    tuple(sessions)):
            msg = json.loads(data)
            t = msg.get("tokens") or {}
            usage["input"] += t.get("input", 0)
            usage["output"] += t.get("output", 0)
            usage["reasoning"] += t.get("reasoning", 0)
            usage["cache_read"] += (t.get("cache") or {}).get("read", 0)
            usage["cache_write"] += (t.get("cache") or {}).get("write", 0)
            cost += msg.get("cost") or 0
            turns += 1
        conn.close()
    version = sh(str(OPENCODE), "--version").stdout.strip()
    return stdout, {"exit_code": code, "timed_out": timed_out, "wall_seconds": round(wall, 1),
                    "tokens": usage, "api_cost_usd": round(cost, 6), "turns": turns,
                    "limits": {"before": before, "after": after}, "harness_version": version}


def grade(workdir, hidden):
    tampered = bool(sh("git", "status", "--porcelain", "--", "tests", cwd=workdir).stdout.strip())
    sh("git", "checkout", "--", "tests", cwd=workdir)
    sh("git", "clean", "-fdq", "--", "tests", cwd=workdir)
    visible_ok, total, failed = gen.grade_dir(workdir, hidden)
    diff = sh("git", "diff", "--", gen.PKG, cwd=workdir).stdout
    return diff, {
        "visible_tests_pass": visible_ok,
        "hidden_passed": total - len(failed),
        "hidden_total": total,
        "hidden_failed": failed,
        "score": round((total - len(failed)) / total, 3) if total else 0,
        "passed": visible_ok and not failed and not tampered,
        "tests_tampered": tampered,
        "diff_lines": sum(1 for l in diff.splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")),
    }


def day_of(seed):
    return seed if re.fullmatch(r"\d{4}-\d\d-\d\d", seed) else dt.date.today().isoformat()


def run(key, seed):
    spec = MODELS[key]
    stamp = dt.datetime.now(dt.timezone.utc)
    # Only what describes the run itself goes into the record; the site's names and grouping
    # come from MODELS when summarize.py runs.
    record = {"date": day_of(seed), "started_at": stamp.isoformat(timespec="seconds"), "model_key": key,
              **{k: spec[k] for k in ("harness", "model", "plan")}, "effort": effort_of(spec),
              "task_version": gen.VERSION, "seed": seed}
    # /tmp keeps the task away from this repo, and the hidden tests stay in memory until the
    # model is done, so there is nothing to find.
    scratch = Path(tempfile.mkdtemp(prefix=f"canary-{key}-", dir="/tmp"))
    try:
        variant = gen.generate(seed, scratch)
        workdir, hidden = scratch / "task", scratch / "hidden.py"
        hidden_text = hidden.read_text()
        hidden.unlink()
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.name=canary", "-c", "user.email=canary@localhost", "commit", "-qm", "task"]):
            sh(*cmd, cwd=workdir)
        runner = {"claude": run_claude, "codex": run_codex, "opencode": run_opencode}[spec["harness"]]
        transcript, outcome = runner(spec, workdir)
        hidden.write_text(hidden_text)
        diff, grades = grade(workdir, hidden)
        # Any sign the model looked at the harness, the reference code or the hidden tests.
        leaks = sorted({m for m in (str(ROOT), "model-canary", "schedule_task", "gen.py", "hidden.py", "test_hidden")
                        if m in transcript})
        limits = outcome["limits"]
        # Past 100% the run is paid from credits, so its limit readings say nothing about the plan.
        over = any((reading or {}).get(w) is not None and reading[w] >= 1
                   for reading in limits.values() for w in ("five_hour", "seven_day"))
        record.update({"variant": variant, **outcome, "over_limit": over, **grades})
        # The CLI itself failed (a limit, an outage, a login problem): not the model's score.
        record["infra_error"] = outcome["exit_code"] not in (0, None) and not grades["diff_lines"]
        record["harness_seen"] = leaks
    except Exception as err:
        # The harness broke before the model could finish (a missing CLI, say). Record it like
        # any other infra error, in the same shape, so the other models still run and the
        # day's freshness check sees the gap.
        transcript, diff = traceback.format_exc(), ""
        record.update({"variant": None, "exit_code": None, "timed_out": False, "wall_seconds": 0,
                       "tokens": {}, "api_cost_usd": None, "turns": None,
                       "limits": {"before": None, "after": None}, "harness_version": None,
                       "over_limit": False, "visible_tests_pass": False, "hidden_passed": 0,
                       "hidden_total": 0, "hidden_failed": [], "score": 0, "passed": False,
                       "tests_tampered": False, "diff_lines": 0, "infra_error": True,
                       "harness_seen": [], "error": f"{type(err).__name__}: {err}"})
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    values = secrets()
    out_dir = RESULTS / "runs" / record["date"] / key
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcript.jsonl").write_text(redact(transcript, values))
    (out_dir / "fix.diff").write_text(redact(diff, values))
    (out_dir / "result.json").write_text(redact(json.dumps(record, indent=2), values) + "\n")
    with open(RESULTS / "runs.jsonl", "a") as f:
        f.write(redact(json.dumps(record), values) + "\n")
    print(f"{key}: passed={record['passed']} hidden={record['hidden_passed']}/{record['hidden_total']} "
          f"time={record['wall_seconds']}s limits={record['limits']}"
          + (f" infra_error={record.get('error') or True}" if record["infra_error"] else ""))
    return record


if __name__ == "__main__":
    args = sys.argv[1:]
    seed = dt.date.today().isoformat()
    if "--seed" in args:
        i = args.index("--seed")
        seed = args[i + 1]
        del args[i:i + 2]
    keys = args or ["all"]
    if keys == ["all"]:
        keys = [k for k in MODELS if active(k, day_of(seed))]
    failed = [k for k in keys if run(k, seed)["infra_error"]]
    if failed:
        print(f"No result for: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)
