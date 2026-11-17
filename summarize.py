#!/usr/bin/env python3
"""Build results/summary.json from results/runs.jsonl for the site.

Only runs of the current task version count: a new task version starts every model's history
fresh, since its times and scores aren't comparable with the old task's.
"""
import json
import re
import statistics
from pathlib import Path

from run import MODELS

RESULTS = Path(__file__).resolve().parent / "results"
TASK_VERSION = 3
HARNESS_NAMES = {"claude": "Claude Code", "codex": "Codex", "opencode": "OpenCode"}
VENDOR_OF_HARNESS = {"claude": "Anthropic", "codex": "OpenAI", "opencode": "DeepSeek"}


def events(runs):
    """Each change of CLI version or plan after a harness's first run, so the site can mark the
    day on the chart instead of leaving a jump in time or tokens to look like the model."""
    out, seen = [], {}
    for r in sorted(runs, key=lambda r: r["started_at"]):
        harness = r.get("harness")
        for kind, value in (("harness", r.get("harness_version")), ("plan", r.get("plan"))):
            if not value:
                continue
            key = (harness, kind)
            if key in seen and seen[key] != value:
                version = re.search(r"\d+(?:\.\d+)+", value)
                text = (f"{HARNESS_NAMES.get(harness, harness)} {version.group(0) if version else value}"
                        if kind == "harness" else f"Plan: {value}")
                out.append({"date": r["date"], "vendor": VENDOR_OF_HARNESS.get(harness, harness), "kind": kind, "text": text})
            seen[key] = value
    # One marker per vendor, kind and day.
    return list({(e["date"], e["vendor"], e["kind"]): e for e in out}.values())


def main():
    runs = [json.loads(l) for l in (RESULTS / "runs.jsonl").read_text().splitlines() if l.strip()]
    runs = [r for r in runs if r.get("task_version") == TASK_VERSION]
    # Failed runs I've checked by hand (see README). A run whose failure was the harness's
    # fault, not the model's, is left out like an infra error.
    reviews = json.loads((RESULTS / "reviews.json").read_text())
    review = lambda r: reviews.get(r["date"], {}).get(r["model_key"]) if not r["passed"] else None
    counted = [r for r in runs if not r.get("infra_error") and not r.get("harness_seen")
               and (review(r) or {}).get("cause") != "harness"]
    # The day the site reports is the last day a model actually ran, so a day where every run
    # broke doesn't look like fresh results.
    latest = counted[-1]
    models = {}
    # Models in run.py's order, so a new version sits next to the one before it.
    seen = dict.fromkeys(r["model_key"] for r in counted)
    for key in [k for k in MODELS if k in seen] + [k for k in seen if k not in MODELS]:
        mine = [r for r in counted if r["model_key"] == key]
        spec = MODELS.get(key, {})
        recent = mine[-30:]
        times = [r["wall_seconds"] for r in recent if not r["timed_out"]]
        until = spec.get("until")
        models[key] = {
            "model": mine[-1]["model"],
            "label": spec.get("label"),
            "vendor": spec.get("vendor"),
            "family": spec.get("family"),
            "base": spec.get("base"),
            "successor": spec.get("successor"),
            # Gone from run.py, or past its last day.
            "retired": (until if until and until < latest["date"] else None) if key in MODELS else mine[-1]["date"],
            "until": until,
            "first": mine[0]["date"],
            "last": mine[-1]["date"],
            "plan": mine[-1]["plan"],
            # OpenCode never took an effort setting, though early runs logged one.
            "effort": "default" if mine[-1].get("harness") == "opencode" else mine[-1].get("effort"),
            "runs": len(mine),
            "pass_rate_30": round(sum(r["passed"] for r in recent) / len(recent), 3),
            "mean_score_30": round(sum(r.get("score", 0) for r in recent) / len(recent), 3),
            "median_seconds_30": round(statistics.median(times), 1) if times else None,
            "latest": {k: mine[-1].get(k) for k in (
                "date", "seed", "passed", "score", "hidden_passed", "hidden_total", "wall_seconds",
                "tokens", "api_cost_usd", "limits", "harness_version")},
            "history": [{**{k: r.get(k) for k in ("date", "passed", "score", "wall_seconds", "over_limit",
                                                  "limits", "api_cost_usd", "turns", "harness_version", "plan")},
                         "tokens": sum((r.get("tokens") or {}).values()) - (r.get("tokens") or {}).get("reasoning", 0),
                         "output": (r.get("tokens") or {}).get("output", 0),
                         **({"review": review(r)} if review(r) else {})}
                        for r in mine],
        }
    (RESULTS / "summary.json").write_text(json.dumps({
        "schema": 2, "task_version": TASK_VERSION,
        "updated": latest["started_at"], "date": latest["date"], "variant": latest.get("variant"),
        "hidden_total": latest.get("hidden_total"), "events": events(counted), "models": models}, indent=2) + "\n")


if __name__ == "__main__":
    main()
