#!/usr/bin/env python3
"""Build results/summary.json from results/runs.jsonl for the site."""
import json
import statistics
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def main():
    runs = [json.loads(l) for l in (RESULTS / "runs.jsonl").read_text().splitlines() if l.strip()]
    runs = [r for r in runs if r.get("task_version") == 3]
    models = {}
    for key in dict.fromkeys(r["model_key"] for r in runs):
        mine = [r for r in runs if r["model_key"] == key and not r.get("infra_error") and not r.get("harness_seen")]
        if not mine:
            continue
        recent = mine[-30:]
        times = [r["wall_seconds"] for r in recent if not r["timed_out"]]
        models[key] = {
            "model": mine[-1]["model"],
            "plan": mine[-1]["plan"],
            "runs": len(mine),
            "pass_rate_30": round(sum(r["passed"] for r in recent) / len(recent), 3),
            "mean_score_30": round(sum(r.get("score", 0) for r in recent) / len(recent), 3),
            "median_seconds_30": round(statistics.median(times), 1) if times else None,
            "latest": {k: mine[-1].get(k) for k in (
                "date", "seed", "passed", "score", "hidden_passed", "hidden_total", "wall_seconds",
                "tokens", "api_cost_usd", "limits", "harness_version")},
            "history": [{**{k: r.get(k) for k in ("date", "passed", "score", "wall_seconds", "over_limit",
                                                  "limits", "api_cost_usd", "turns")},
                         "tokens": sum((r.get("tokens") or {}).values()) - (r.get("tokens") or {}).get("reasoning", 0),
                         "output": (r.get("tokens") or {}).get("output", 0)}
                        for r in mine],
        }
    latest = runs[-1]
    (RESULTS / "summary.json").write_text(json.dumps({
        "updated": latest["started_at"], "date": latest["date"], "variant": latest.get("variant"),
        "hidden_total": latest.get("hidden_total"), "models": models}, indent=2) + "\n")


if __name__ == "__main__":
    main()
