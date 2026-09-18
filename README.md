# GridWise — Smart Campus Energy Optimization Service
**BUP CSE Fest 2026 · Hackathon Submission**

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/Rushu41/BUP_HACKATHON)
[![Railway Deployment](https://img.shields.io/badge/Railway-Production%20Live-success?logo=railway)](https://buphackathon-production-ad62.up.railway.app)
[![API Documentation](https://img.shields.io/badge/Swagger%20UI-Interactive%20Docs-informational?logo=swagger)](https://buphackathon-production-ad62.up.railway.app/docs)

GridWise is an enterprise-grade, high-performance energy scheduling HTTP service. It combines natural language operator notes interpretation via a constrained Large Language Model (LLM), deterministic validation guardrails, and a Mixed-Integer Linear Programming (MILP) mathematical optimizer to produce a cost-minimal 24-hour dispatch schedule that strictly satisfies electrical energy balances, physical battery constraints, time-of-use tariffs, and operational directives.

---

## 🌐 Production Deployed Service (Railway)

The backend service is fully deployed and accessible in the cloud:

* **Base URL**: `https://buphackathon-production-ad62.up.railway.app`
* **Interactive API Docs (Swagger UI)**: [https://buphackathon-production-ad62.up.railway.app/docs](https://buphackathon-production-ad62.up.railway.app/docs)
* **OpenAPI Schema**: `https://buphackathon-production-ad62.up.railway.app/openapi.json`
* **Health Check Endpoint**: `GET https://buphackathon-production-ad62.up.railway.app/health`
* **Optimization Endpoint**: `POST https://buphackathon-production-ad62.up.railway.app/optimize-energy`

---

## 1. System Architecture

```
FastAPI HTTP Request (POST /optimize-energy)
      ↓
[1] Request & Schema Validation (Pydantic v2)
      ↓
[2] LLM Operator-Note Interpreter (Google GenAI Gemini)
      ↓
[3] Deterministic Guardrails (Strict bounds & canonical normalization)
      ↓
[4] Directive Application (Mathematical constraint derivation)
      ↓
[5] Mathematical Optimizer (PuLP + CBC MILP Solver)
      ↓
[6] Independent Hourly-Plan Validator (Replays physics & recalculates totals)
      ↓
[7] Deterministic Plan Summary & Canonical JSON Response
```

### Pipeline Responsibilities:
1. **LLM Interpreter**: Handles natural-language understanding. Maps 1–3 operator notes into structured directive candidates adhering strictly to JSON schema.
   - **What it does**: Parses temporal phrases (e.g., "noon to 2 PM", "between 13:00 and 15:00"), reduction fractions, reserve thresholds, and grid caps.
   - **What it does NOT do**: It does NOT compute dispatch numbers, does NOT calculate costs or totals, does NOT modify tariffs or load profiles, and does NOT invent unstated rules.
2. **Deterministic Guardrails**: Authoritative validation layer before optimization. Rejects unsupported directive types, ensures exact sequence mapping, verifies numeric bounds, strictly rejects booleans for numeric fields, and enforces start-inclusive/end-exclusive hours.
3. **Mathematical Optimizer**: Solves the 24-hour MILP cost minimization objective:
   $$\min \sum_{h=0}^{23} \text{grid}[h] \times \text{tariff}[h]$$
   Honors hourly energy balance, effective solar limits, active reserves, charge/discharge rates, window bans, grid caps, and mandatory end-of-day battery neutrality ($\text{energy}[23] = \text{initial}$).
4. **Independent Final Validator**: Replays the entire 24-hour plan from scratch independently of the solver. Audits non-negativity, rates, bounds, balance, and directives, then recalculates `total_grid_kwh`, `total_cost_bdt`, and `peak_grid_kwh`.

---

## 2. Supported Directives

GridWise supports exactly six canonical directive types:
- `solar_reduction`: Usable PV output reduced to a fraction (e.g., `factor=0.20` for an 80% reduction).
- `minimum_battery_reserve`: Elevates minimum battery energy during designated hours (e.g., `minimum_energy_kwh=100.0`).
- `no_charge_window`: Prohibits battery charging during listed hours (`charge=0`).
- `no_discharge_window`: Prohibits battery discharging during listed hours (`discharge=0`).
- `max_grid_window`: Imposes a ceiling on grid power draw (`grid <= max_grid_kwh`).
- `no_op`: Irrelevant note (cafeteria, sports, seminars) marked with `applies=false` and `structured_adjustment=null`.

---

## 3. Environment Configuration

All settings are unified and managed through `app/config.py`:

| Variable Name | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | Optional / Recommended | `""` | Primary API key for Google GenAI provider (aliases `GEMINI_API_KEY`) |
| `LLM_MODEL` | Optional | `gemini-3.1-flash-lite` | LLM model identifier |
| `LLM_BASE_URL` | Optional | `""` | Custom provider base URL if using a proxy |
| `LLM_TIMEOUT_SECONDS` | Optional | `25.0` | Timeout threshold for provider calls |
| `PORT` | Optional | `8000` | HTTP service port |
| `LOG_LEVEL` | Optional | `INFO` | Application logging level |

---

## 4. Local Installation & Setup

### Prerequisites
- Python 3.10+
- Virtual environment tool (`venv`)
- CBC MILP Solver (`coinor-cbc`)

### Setup Instructions
```bash
# 1. Clone repository and navigate to workspace root
git clone https://github.com/Rushu41/BUP_HACKATHON.git
cd BUP_HACKATHON

# 2. Create and activate a clean virtual environment
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Linux/macOS:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment credentials
cp .env.example .env
# Edit .env and supply your LLM_API_KEY
```

---

## 5. Running the Service Locally

Start the FastAPI application with Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
The service becomes ready in less than 2 seconds at `http://localhost:8000`.

---

## 6. API Endpoints & Verification

### 1. Health Check (`GET /health`)
```bash
# Live Production
curl -X GET https://buphackathon-production-ad62.up.railway.app/health

# Local
curl -X GET http://localhost:8000/health
```
**Response (HTTP 200)**:
```json
{
  "status": "ok"
}
```

### 2. Energy Optimization (`POST /optimize-energy`)
```bash
# Live Production
curl -X POST https://buphackathon-production-ad62.up.railway.app/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "DEMO-01",
    "operator_notes": [
      "Facilities will wash the rooftop solar panels from noon until 2 PM. Usable solar should be treated as 25% of forecast.",
      "The sports office moved next month registration deadline."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 90, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 1, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 2, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 3, "demand_kwh": 80, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 4, "demand_kwh": 85, "solar_kwh": 0, "tariff_bdt_per_kwh": 5},
      {"hour": 5, "demand_kwh": 95, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
      {"hour": 6, "demand_kwh": 110, "solar_kwh": 5, "tariff_bdt_per_kwh": 8},
      {"hour": 7, "demand_kwh": 130, "solar_kwh": 20, "tariff_bdt_per_kwh": 10},
      {"hour": 8, "demand_kwh": 150, "solar_kwh": 50, "tariff_bdt_per_kwh": 12},
      {"hour": 9, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14},
      {"hour": 10, "demand_kwh": 175, "solar_kwh": 130, "tariff_bdt_per_kwh": 16},
      {"hour": 11, "demand_kwh": 180, "solar_kwh": 160, "tariff_bdt_per_kwh": 16},
      {"hour": 12, "demand_kwh": 185, "solar_kwh": 180, "tariff_bdt_per_kwh": 15},
      {"hour": 13, "demand_kwh": 180, "solar_kwh": 170, "tariff_bdt_per_kwh": 14},
      {"hour": 14, "demand_kwh": 170, "solar_kwh": 140, "tariff_bdt_per_kwh": 13},
      {"hour": 15, "demand_kwh": 165, "solar_kwh": 90, "tariff_bdt_per_kwh": 14},
      {"hour": 16, "demand_kwh": 170, "solar_kwh": 45, "tariff_bdt_per_kwh": 18},
      {"hour": 17, "demand_kwh": 185, "solar_kwh": 10, "tariff_bdt_per_kwh": 22},
      {"hour": 18, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 28},
      {"hour": 19, "demand_kwh": 215, "solar_kwh": 0, "tariff_bdt_per_kwh": 30},
      {"hour": 20, "demand_kwh": 205, "solar_kwh": 0, "tariff_bdt_per_kwh": 26},
      {"hour": 21, "demand_kwh": 175, "solar_kwh": 0, "tariff_bdt_per_kwh": 18},
      {"hour": 22, "demand_kwh": 135, "solar_kwh": 0, "tariff_bdt_per_kwh": 10},
      {"hour": 23, "demand_kwh": 105, "solar_kwh": 0, "tariff_bdt_per_kwh": 7}
    ],
    "battery": {
      "capacity_kwh": 200,
      "initial_energy_kwh": 100,
      "minimum_energy_kwh": 20,
      "max_charge_kwh_per_hour": 50,
      "max_discharge_kwh_per_hour": 50
    }
  }'
```

---

## 7. Testing Suites & Verification

### 1. Run Complete Unit and Integration Test Suite
```bash
python -m pytest tests/
```

### 2. Run Official 10 Public Sample Cases
Executes all 10 official cases through the end-to-end pipeline and validates optimal costs:
```bash
# Offline deterministic mock verification:
python scripts/test_public_cases.py --mock

# Live local verification (in-process):
python scripts/test_public_cases.py

# Live deployed Railway verification (remote):
python scripts/test_public_cases.py --remote
```

### 3. Verify Deployed Live Backend Diagnostics
Validates health probe, OpenAPI docs, HTTP 400 schema error sanitization, and end-to-end optimization:
```bash
python scripts/test_live_backend.py
```

### 4. Stress and Scale Testing
```bash
# Local:
python scripts/run_100_tests.py

# Against live Railway backend (with rate limit pacing):
python scripts/run_100_tests.py --remote --limit 10
```

---

## 8. Docker Deployment

### Build Container Image
```bash
docker build -t gridwise-app .
```

### Run Container Service
```bash
docker run -d -p 8000:8000 -e LLM_API_KEY="your-api-key" --name gridwise gridwise-app
```

### Container Health Probe
```bash
curl http://localhost:8000/health
```

---

## 9. Security & Secret Handling
- **No Credentials Committed**: `.env` and credential files are strictly excluded via `.gitignore` and `.dockerignore`.
- **Zero Leakage**: FastAPI global exception handlers sanitize unhandled errors into controlled HTTP 500 responses with zero tracebacks or authorization header leaks.
- **Controlled Error Codes**: Known domain exceptions (`REQUEST_VALIDATION_ERROR`, `GUARDRAIL_VALIDATION_ERROR`, `OPTIMIZATION_ERROR`, `PLAN_VALIDATION_ERROR`, `PROVIDER_ERROR`) return structured messages without exposing internal stack traces.

---

## 10. Known Limitations
- **External Provider Dependency**: Live interpretation requires outbound internet connectivity to Google GenAI endpoints.
- **Round-Trip Battery Efficiency**: Modeled at 100% per official preliminary competition specification.
- **Grid Export**: Solar curtailment is enforced; grid feed-in/export is non-negative ($grid \ge 0$).
