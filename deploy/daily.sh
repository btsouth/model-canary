#!/usr/bin/env bash
# Run the canary for every model, then publish the results. A model that couldn't run is
# recorded as an infra error and the rest still run; the service then fails so the problem
# shows up, after whatever did run is published. The freshness check in
# .github/workflows/freshness.yml opens an issue when a day or a model is missing.
set -euo pipefail
cd "$(dirname "$0")/.."
# Claude Code signs in with a long-lived token from `claude setup-token`; a copied login expires.
TOKEN_FILE="$HOME/.config/model-canary/claude-oauth.token"
if [ -r "$TOKEN_FILE" ]; then
  CLAUDE_CODE_OAUTH_TOKEN="$(cat "$TOKEN_FILE")"
  export CLAUDE_CODE_OAUTH_TOKEN
fi
git pull -q --ff-only origin main || true
rc=0
python3 run.py all || rc=$?
# Explain every miss that has no note yet. A failure here must not hold back the results.
python3 review.py || true
python3 summarize.py
git add results
if git commit -qm "Canary results $(date +%F)"; then
  git push -q origin main
  # Ask btso.dev to pull the new results now instead of at its next scheduled refresh.
  gh api -X POST repos/btsouth/btso.dev/dispatches -f event_type=refresh >/dev/null || true
fi
exit "$rc"
