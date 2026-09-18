import argparse
import json
import os
import sys
import time
import httpx

WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

DEFAULT_REMOTE_URL = "https://buphackathon-production-ad62.up.railway.app"


def get_client(target_url: str | None = None):
    if target_url:
        return httpx.Client(base_url=target_url.rstrip("/"), timeout=90.0), False
    else:
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app), True


def run_tests(target_url: str | None = None, limit: int | None = None, delay: float = 4.2):
    cases_file = os.path.join(WORKSPACE_DIR, "100_hidden_cases.json")
    if not os.path.exists(cases_file):
        cases_file = os.path.join(WORKSPACE_DIR, "public_cases.json")

    with open(cases_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        cases = data["cases"] if isinstance(data, dict) and "cases" in data else data

    if limit is not None and limit > 0:
        cases = cases[:limit]

    client, is_local = get_client(target_url)
    mode_str = f"remote backend: {target_url}" if target_url else "local in-process TestClient"
    print(f"Running {len(cases)} tests against {mode_str}...")

    successes = 0
    failures = 0
    latencies = []

    try:
        for i, case in enumerate(cases):
            case_input = case["input"] if "input" in case else case
            scenario_id = case_input.get("scenario_id", f"CASE-{i}")

            start_time = time.time()
            try:
                response = client.post("/optimize-energy", json=case_input)
                latency = time.time() - start_time
                latencies.append(latency)

                if response.status_code == 200:
                    res_data = response.json()
                    if res_data.get("scenario_id") == scenario_id and "hourly_plan" in res_data:
                        successes += 1
                        print(f"[{i+1}/{len(cases)}] {scenario_id}: PASS ({latency:.2f}s)")
                    else:
                        print(f"[{i+1}/{len(cases)}] {scenario_id}: FAILED VALIDATION -> {res_data}")
                        failures += 1
                else:
                    print(f"[{i+1}/{len(cases)}] {scenario_id}: HTTP {response.status_code} -> {response.text}")
                    failures += 1
            except Exception as e:
                latency = time.time() - start_time
                latencies.append(latency)
                print(f"[{i+1}/{len(cases)}] {scenario_id}: ERROR -> {e}")
                failures += 1

            # Rate limit pacing if more cases remain
            if i < len(cases) - 1 and delay > 0:
                time.sleep(delay)

            if (i + 1) % 10 == 0:
                print(f"Progress: {i+1}/{len(cases)} processed. Success: {successes}, Failures: {failures}")
    finally:
        if hasattr(client, "close"):
            client.close()

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95) if latencies else 0
    p95_latency = latencies[p95_idx] if latencies else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    print("\n=== TEST RESULTS ===")
    print(f"Target: {target_url or 'Local TestClient'}")
    print(f"Total Tests: {len(cases)}")
    print(f"Successes: {successes}")
    print(f"Failures: {failures}")
    print(f"Average Latency: {avg_latency:.2f}s")
    print(f"p95 Latency: {p95_latency:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stress and Regression Test Runner")
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
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of test cases to run (e.g. 5 or 10)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=4.2,
        help="Delay between requests in seconds to avoid LLM rate limit quotas (default: 4.2)",
    )
    args = parser.parse_args()

    target = None
    if args.remote and not args.url:
        target = DEFAULT_REMOTE_URL
    elif args.url:
        target = args.url
    elif os.environ.get("BACKEND_URL"):
        target = os.environ.get("BACKEND_URL")

    run_tests(target_url=target, limit=args.limit, delay=args.delay)
