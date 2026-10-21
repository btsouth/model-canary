#!/usr/bin/env bash
# Run the canary for every model, then publish the results.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull -q --ff-only origin main || true
python3 run.py all
python3 summarize.py
git add results
git commit -qm "Canary results $(date +%F)" || exit 0
git push -q origin main
