"""Diagnostic and functional test suite for the deployed GridWise Railway backend."""

import argparse
import json
import os
import sys
import httpx

DEFAULT_BASE_URL = "https://buphackathon-production-ad62.up.railway.app"


# Prevent pytest from auto-collecting this CLI verification script
__test__ = False


def verify_live_backend(base_url: str = DEFAULT_BASE_URL):
    base_url = base_url.rstrip("/")
    print(f"=" * 60)
    print(f"Testing GridWise Deployed Backend at: {base_url}")
    print(f"=" * 60)

    client = httpx.Client(timeout=60.0)

    # 1. Test Health Endpoint
    print("\n[Test 1] Checking GET /health ...")
    try:
        resp = client.get(f"{base_url}/health")
        print(f"  Status Code: {resp.status_code}")
        print(f"  Response Body: {resp.text}")
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            print("  >>> PASS: Health check endpoint is OK.")
        else:
            print(f"  >>> FAIL: Health endpoint returned unexpected response.")
    except Exception as e:
        print(f"  >>> ERROR connecting to health check: {e}")

    # 2. Test OpenAPI Spec
    print("\n[Test 2] Checking GET /openapi.json ...")
    try:
        resp = client.get(f"{base_url}/openapi.json")
        print(f"  Status Code: {resp.status_code}")
        if resp.status_code == 200:
            openapi_data = resp.json()
            paths = list(openapi_data.get("paths", {}).keys())
            print(f"  Registered routes: {paths}")
            print("  >>> PASS: OpenAPI documentation is available.")
        else:
            print(f"  >>> FAIL: OpenAPI returned status {resp.status_code}")
    except Exception as e:
        print(f"  >>> ERROR fetching OpenAPI spec: {e}")

    # 3. Test Validation Rejection (HTTP 400)
    print("\n[Test 3] Checking POST /optimize-energy input validation (malformed body) ...")
    try:
        resp = client.post(f"{base_url}/optimize-energy", json={"invalid_field": "test"})
        print(f"  Status Code: {resp.status_code}")
        print(f"  Response Body: {resp.text}")
        if resp.status_code == 400 and resp.json().get("error") == "REQUEST_VALIDATION_ERROR":
            print("  >>> PASS: Schema guardrails rejected malformed payload with HTTP 400.")
        else:
            print(f"  >>> FAIL: Expected HTTP 400 REQUEST_VALIDATION_ERROR.")
    except Exception as e:
        print(f"  >>> ERROR sending malformed request: {e}")

    # 4. Test Live Scenario Optimization
    print("\n[Test 4] Checking POST /optimize-energy with official Sample Scenario 1 ...")
    sample_path = os.path.join(os.path.dirname(__file__), "..", "public_cases.json")
    sample_case = None
    if os.path.exists(sample_path):
        with open(sample_path, "r", encoding="utf-8") as f:
            cases_data = json.load(f)
            cases_list = cases_data["cases"] if isinstance(cases_data, dict) and "cases" in cases_data else cases_data
            if cases_list:
                sample_case = cases_list[0]["input"] if "input" in cases_list[0] else cases_list[0]

    if not sample_case:
        print("  >>> SKIP: Could not find sample case in public_cases.json")
        return

    try:
        resp = client.post(f"{base_url}/optimize-energy", json=sample_case)
        print(f"  Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Scenario ID: {data.get('scenario_id')}")
            print(f"  Directives count: {len(data.get('directive_interpretation', []))}")
            print(f"  Hourly plan count: {len(data.get('hourly_plan', []))}")
            print(f"  Total Cost (BDT): {data.get('total_cost_bdt')}")
            print(f"  Plan Summary: {data.get('plan_summary')}")
            print("  >>> PASS: Full optimization pipeline succeeded end-to-end!")
        elif resp.status_code == 500:
            error_data = resp.json()
            err_type = error_data.get("error")
            detail = error_data.get("detail", "")
            print(f"  Error Type: {err_type}")
            print(f"  Detail: {detail}")
            if "LLM API key is not configured" in detail:
                print("\n  [!] DIAGNOSIS:")
                print("  The Railway deployment is healthy and responding, but the environment variable")
                print("  'LLM_API_KEY' (or 'GEMINI_API_KEY') is not set in your Railway project dashboard.")
                print("  To fix this:")
                print("    1. Open your Railway dashboard: https://railway.com/dashboard")
                print("    2. Click on project 'buphackathon'")
                print("    3. Click on the active service")
                print("    4. Navigate to the 'Variables' tab")
                print("    5. Click '+ New Variable' and add:")
                print("         LLM_API_KEY = <your_gemini_api_key>")
                print("         LLM_MODEL   = gemini-3.1-flash-lite")
                print("    6. Railway will automatically redeploy the service with the key enabled.")
        else:
            print(f"  Unexpected response: {resp.status_code} -> {resp.text}")
    except Exception as e:
        print(f"  >>> ERROR sending optimization request: {e}")

    client.close()
    print(f"\n{'=' * 60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Live Deployed Backend")
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_BASE_URL,
        help=f"Target base URL (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()
    verify_live_backend(args.url)
