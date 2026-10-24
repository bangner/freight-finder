#!/usr/bin/env bash
# Turn a LaunchDarkly flag OFF: the remediation step for a bad release.
#
# Usage:  scripts/rollback.sh [flag-key]     (default: eta-predictions)
#
# Safe to run more than once: turning off a flag that is already off changes nothing.
# The app does not need to be restarted; every open browser updates within a second.
#
# It uses, in order:
#   1. LD_TRIGGER_URL: the flag trigger you created on eta-predictions with the action
#      "Turn the flag off" (docs/LAUNCHDARKLY_SETUP.md, step 4). Needs no API token.
#   2. LD_API_TOKEN + LD_PROJECT_KEY + LD_ENV_KEY: the REST API, for any flag.
#      LD_API_BASE defaults to https://app.launchdarkly.com (change it for other instances).
#
# Values come from the environment or from .env in the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

FLAG_KEY="${1:-eta-predictions}"
LD_API_BASE="${LD_API_BASE:-https://app.launchdarkly.com}"

if [[ -n "${LD_TRIGGER_URL:-}" && "$FLAG_KEY" == "eta-predictions" ]]; then
  # The trigger URL is a secret: anyone holding it can turn the flag off. Never log it.
  curl --fail-with-body --silent --show-error --output /dev/null -X POST "$LD_TRIGGER_URL"
  echo "Rollback sent through the flag trigger: $FLAG_KEY is now off."
  exit 0
fi

if [[ -z "${LD_API_TOKEN:-}" || -z "${LD_PROJECT_KEY:-}" || -z "${LD_ENV_KEY:-}" ]]; then
  echo "Set LD_TRIGGER_URL (for eta-predictions), or LD_API_TOKEN, LD_PROJECT_KEY and LD_ENV_KEY." >&2
  exit 1
fi

# Semantic patch: describes the change ("turn the flag off") instead of editing JSON by hand.
curl --fail-with-body --silent --show-error --output /dev/null \
  -X PATCH "${LD_API_BASE}/api/v2/flags/${LD_PROJECT_KEY}/${FLAG_KEY}" \
  -H "Authorization: ${LD_API_TOKEN}" \
  -H "Content-Type: application/json; domain-model=launchdarkly.semanticpatch" \
  --data "{\"environmentKey\": \"${LD_ENV_KEY}\", \"comment\": \"Rollback via scripts/rollback.sh\", \"instructions\": [{\"kind\": \"turnFlagOff\"}]}"
echo "Rollback sent through the REST API: $FLAG_KEY is now off in ${LD_ENV_KEY}."
