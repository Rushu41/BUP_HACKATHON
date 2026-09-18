"""Standalone public sample case test runner for GridWise.

Executes all 10 official public cases through the complete application pipeline:
Request validation -> LLM interpretation -> Guardrails -> Optimizer -> Validator -> Recalculated totals.

Supports:
- Live LLM execution if LLM_API_KEY (or GEMINI_API_KEY) is configured.
- Deterministic mock mode (default if no key is present or when --mock is passed).
"""

import argparse
import asyncio
import json
import os
import sys
from unittest.mock import patch

# Ensure workspace root is in sys.path
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

import httpx
from app.config import settings
from app.orchestrator import process_scenario
from app.schemas import OptimizeEnergyRequest, OptimizeEnergyResponse
from app.validator import validate_hourly_plan


def load_official_cases() -> list[dict]:
    """Loads official sample cases from BUP sample pack or public_cases.json."""
    pack_path = os.path.join(
        WORKSPACE_DIR, "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
    )
    if os.path.exists(pack_path):
        with open(pack_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data["cases"]

    fallback_path = os.path.join(WORKSPACE_DIR, "public_cases.json")
    if os.path.exists(fallback_path):
        with open(fallback_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data["cases"] if isinstance(data, dict) and "cases" in data else data

    raise FileNotFoundError("Could not find official public sample cases JSON pack.")


async def run_single_case(
    case: dict,
    use_mock: bool = False,
    target_url: str | None = None,
) -> tuple[bool, str]:
    """Runs a single sample case through the end-to-end pipeline and checks validity and cost."""
    case_id = case.get("id", case.get("input", {}).get("scenario_id", "UNKNOWN"))
    case_input = case["input"] if "input" in case else case
    expected_output = case.get("expected_output", {})
    expected_directives = expected_output.get(
        "directive_interpretation", case.get("expected_directives", [])
    )

    try:
        request = OptimizeEnergyRequest(**case_input)
    except Exception as e:
        return False, f"[{case_id}] Request validation failed: {str(e)}"

    if target_url:
        endpoint = f"{target_url.rstrip('/')}/optimize-energy"
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(endpoint, json=case_input)
            if resp.status_code != 200:
                return False, f"[{case_id}] HTTP {resp.status_code} from {endpoint}: {resp.text}"
            response = OptimizeEnergyResponse(**resp.json())
        except Exception as e:
            return False, f"[{case_id}] Network / execution error against {endpoint}: {str(e)}"
    else:
        try:
            if use_mock:
                mock_response = json.dumps(expected_directives)
                with patch("app.llm_interpreter.call_llm", return_value=mock_response):
                    response = await process_scenario(request)
            else:
                response = await process_scenario(request)
        except Exception as e:
            return False, f"[{case_id}] Pipeline execution failed: {str(e)}"

    # 1. Validate directive interpretation semantics
    actual_directives = [
        d.model_dump() if hasattr(d, "model_dump") else d
        for d in response.directive_interpretation
    ]
    if len(actual_directives) != len(expected_directives):
        return (
            False,
            f"[{case_id}] Interpretation count mismatch: expected {len(expected_directives)}, got {len(actual_directives)}\n"
            f"Expected: {json.dumps(expected_directives, indent=2)}\n"
            f"Actual: {json.dumps(actual_directives, indent=2)}",
        )

    for i, (act, exp) in enumerate(zip(actual_directives, expected_directives)):
        if act["directive_type"] != exp["directive_type"]:
            return (
                False,
                f"[{case_id}] Note {i} directive_type mismatch: expected {exp['directive_type']}, got {act['directive_type']}",
            )
        if act["applies"] != exp["applies"]:
            return (
                False,
                f"[{case_id}] Note {i} applies mismatch: expected {exp['applies']}, got {act['applies']}",
            )
        if exp["applies"]:
            exp_adj = exp.get("structured_adjustment", {})
            act_adj = act.get("structured_adjustment", {})
            if exp_adj.get("hours") != act_adj.get("hours"):
                return (
                    False,
                    f"[{case_id}] Note {i} hours mismatch: expected {exp_adj.get('hours')}, got {act_adj.get('hours')}",
                )

    # 2. Independent audit of returned hourly_plan
    plan_dicts = [
        p.model_dump() if hasattr(p, "model_dump") else p
        for p in response.hourly_plan
    ]
    try:
        recalc_totals = validate_hourly_plan(
            hours=request.hours,
            battery=request.battery,
            directives=actual_directives,
            hourly_plan=plan_dicts,
        )
    except Exception as e:
        return False, f"[{case_id}] Independent plan validation rejected schedule: {str(e)}"

    # 3. Verify recalculated totals match response
    if abs(recalc_totals["total_grid_kwh"] - response.total_grid_kwh) > 0.01:
        return False, f"[{case_id}] Total grid mismatch between plan and response"
    if abs(recalc_totals["total_cost_bdt"] - response.total_cost_bdt) > 0.01:
        return False, f"[{case_id}] Total cost mismatch between plan and response"
    if abs(recalc_totals["peak_grid_kwh"] - response.peak_grid_kwh) > 0.01:
        return False, f"[{case_id}] Peak grid mismatch between plan and response"

    # 4. Compare optimal cost against official reference
    if "total_cost_bdt" in expected_output:
        exp_cost = float(expected_output["total_cost_bdt"])
        act_cost = float(response.total_cost_bdt)
        diff = abs(exp_cost - act_cost)
        if diff > 0.01:
            return (
                False,
                f"[{case_id}] Cost difference {diff:.2f} BDT exceeds tolerance (Expected: {exp_cost:.2f}, Actual: {act_cost:.2f})",
            )

    return True, f"{case_id} PASS"


DEFAULT_REMOTE_URL = "https://buphackathon-production-ad62.up.railway.app"


async def main():
    parser = argparse.ArgumentParser(description="GridWise Public Sample Case Runner")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock LLM mode even if API key is configured",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help=f"Target backend base URL (e.g. {DEFAULT_REMOTE_URL})",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help=f"Execute tests directly against deployed Railway backend ({DEFAULT_REMOTE_URL})",
    )
    args = parser.parse_args()

    target_url = None
    if args.remote and not args.url:
        target_url = DEFAULT_REMOTE_URL
    elif args.url:
        target_url = args.url
    elif os.environ.get("BACKEND_URL"):
        target_url = os.environ.get("BACKEND_URL")

    cases = load_official_cases()
    print(f"Loaded {len(cases)} official public sample cases.")

    has_key = bool(settings.LLM_API_KEY)
    use_mock = args.mock or (not has_key and not target_url)

    if target_url:
        mode_str = f"REMOTE mode targeting backend: {target_url}"
    elif use_mock:
        mode_str = "MOCK mode (verifying full optimizer + validator + schema pipeline)"
    else:
        mode_str = f"LIVE mode using local process with model '{settings.LLM_MODEL}'"
    print(f"Running in {mode_str}...\n")

    passed = 0
    total = len(cases)
    failures = []

    for case in cases:
        case_id = case.get("id", case.get("input", {}).get("scenario_id", "UNKNOWN"))
        success, message = await run_single_case(case, use_mock=use_mock, target_url=target_url)
        if success:
            passed += 1
            print(f"{case_id} PASS")
        else:
            print(f"{case_id} FAIL")
            failures.append(message)

    print(f"\nPassed {passed}/{total}\n")

    if failures:
        print("Failure Details:")
        for f in failures:
            print("-" * 50)
            print(f)
        sys.exit(1)
    else:
        print("All public cases passed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
