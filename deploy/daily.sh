#!/usr/bin/env bash
# Run the canary for every model, then publish the results.
set -euo pipefail
cd "$(dirname "$0")/.."
# Claude Code signs in with a long-lived token from `claude setup-token`; a copied login expires.
TOKEN_FILE="$HOME/.config/model-canary/claude-oauth.token"
if [ -r "$TOKEN_FILE" ]; then
  CLAUDE_CODE_OAUTH_TOKEN="$(cat "$TOKEN_FILE")"
  export CLAUDE_CODE_OAUTH_TOKEN
fi
git pull -q --ff-only origin main || true
python3 run.py all
python3 summarize.py
git add results
git commit -qm "Canary results $(date +%F)" || exit 0
git push -q origin main
# Ask btso.dev to pull the new results now instead of at its next scheduled refresh.
gh api -X POST repos/btsouth/btso.dev/dispatches -f event_type=refresh >/dev/null || true
