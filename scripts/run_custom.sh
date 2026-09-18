#!/usr/bin/env bash
# Quick custom scenario runner for GridWise

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/export_env.sh" > /dev/null 2>&1

SCENARIO_ID="${1:-CUSTOM-DEMO}"
shift
NOTES=("$@")

if [ ${#NOTES[@]} -eq 0 ]; then
    NOTES=("Panel washing from one until three in the afternoon will leave roughly one-fifth of normal solar output.")
fi

# Build notes JSON array
NOTES_JSON=$(printf '%s\n' "${NOTES[@]}" | jq -R . | jq -s .)

echo "Submitting scenario '$SCENARIO_ID' with ${#NOTES[@]} note(s) to $BASE_URL/optimize-energy ..."

jq -n \
  --arg id "$SCENARIO_ID" \
  --argjson notes "$NOTES_JSON" \
  --argjson hours "$HOURS" \
  --argjson battery "$BATTERY" \
  '{
    scenario_id: $id,
    operator_notes: $notes,
    hours: $hours,
    battery: $battery
  }' | curl -s -X POST "$BASE_URL/optimize-energy" \
  -H "Content-Type: application/json" \
  --data-binary @- | jq .
