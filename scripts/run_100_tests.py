import json
import asyncio
import httpx
import time
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.main import app

# We'll use TestClient for speed and reliability, avoiding network overhead
# Since we are stress-testing logic, this is perfect.
client = TestClient(app)

def run_tests():
    with open("100_hidden_cases.json", "r") as f:
        cases = json.load(f)

    successes = 0
    failures = 0
    latencies = []

    print(f"Running {len(cases)} tests...")

    for i, case in enumerate(cases):
        start_time = time.time()
        
        response = client.post("/optimize-energy", json=case)
        
        latency = time.time() - start_time
        latencies.append(latency)

        if response.status_code == 200:
            data = response.json()
            # Basic checks
            if data["scenario_id"] == case["scenario_id"] and "hourly_plan" in data:
                successes += 1
            else:
                print(f"Case {i} failed validation: {data}")
                failures += 1
        else:
            print(f"Case {i} HTTP {response.status_code}: {response.text}")
            failures += 1

        # Rate limiting to avoid Gemini API quota issues (15 requests per minute = 1 request every 4 seconds)
        # We will sleep for 4.2 seconds just to be safe.
        time.sleep(4.2)
        
        if (i+1) % 10 == 0:
            print(f"Processed {i+1}/100 cases. Successes: {successes}, Failures: {failures}")

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95_latency = latencies[p95_idx] if latencies else 0

    print("\n=== STRESS TEST RESULTS ===")
    print(f"Total Tests: {len(cases)}")
    print(f"Successes: {successes}")
    print(f"Failures: {failures}")
    print(f"Average Latency: {sum(latencies)/len(latencies):.2f}s")
    print(f"p95 Latency: {p95_latency:.2f}s")

if __name__ == "__main__":
    run_tests()
