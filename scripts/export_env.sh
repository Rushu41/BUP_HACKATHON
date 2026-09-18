#!/usr/bin/env bash
# GridWise Environment Setup for WSL/Linux Bash
export BASE_URL="https://buphackathon-production-ad62.up.railway.app"

# Automatically find and extract default hours and battery from available sample JSON
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CASES_FILE=""
if [ -f "$WORKSPACE_ROOT/public_cases.json" ]; then
    CASES_FILE="$WORKSPACE_ROOT/public_cases.json"
elif [ -f "$WORKSPACE_ROOT/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json" ]; then
    CASES_FILE="$WORKSPACE_ROOT/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
fi

if [ -n "$CASES_FILE" ]; then
    export HOURS=$(jq -c 'if type == "array" then .[0].input.hours else .cases[0].input.hours end' "$CASES_FILE")
    export BATTERY=$(jq -c 'if type == "array" then .[0].input.battery else .cases[0].input.battery end' "$CASES_FILE")
    echo "✓ Exported BASE_URL=$BASE_URL"
    echo "✓ Exported HOURS (24-hour profile)"
    echo "✓ Exported BATTERY (capacity, initial/min energy, charge/discharge rates)"
else
    echo "⚠ Could not find public_cases.json to extract HOURS and BATTERY."
fi
