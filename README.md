# GridWise — Smart Campus Energy Optimization Service
**BUP CSE Fest 2026 · Microgrid Optimization & LLM Integration Track**

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/Rushu41/BUP_HACKATHON)
[![Production Status](https://img.shields.io/badge/Railway-Production%20Live-success?logo=railway)](https://buphackathon-production-ad62.up.railway.app)
[![API Specification](https://img.shields.io/badge/OpenAPI%203.1-FastAPI-009688?logo=fastapi)](https://buphackathon-production-ad62.up.railway.app/docs)
[![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python)](https://www.python.org/)
[![Mathematical Solver](https://img.shields.io/badge/Solver-COIN--OR%20CBC%20%28MILP%29-orange)](https://github.com/coin-or/Cbc)

---

## Executive Summary

**GridWise** is a high-performance, deterministic energy management and dispatch optimization service engineered for microgrid operators and smart campuses. The platform reconciles two traditionally conflicting paradigms:
1. **Unstructured Human Language**: Natural language operational logs, maintenance tickets, and situational instructions written by human facility managers.
2. **Rigid Mathematical Optimization**: Exact physical conservation laws, electrochemical battery operating boundaries, time-of-use (ToU) electricity tariffs, and cost-minimizing Mixed-Integer Linear Programming (MILP).

The system utilizes an LLM-assisted interpretation stage constrained by strict JSON schema definitions, deterministic validation guardrails, a formal MILP mathematical model, and an independent physics verification engine that validates all schedules before client delivery.

---

## Production Deployment

The GridWise service is deployed on cloud infrastructure (Railway) with global edge termination and continuous containerized availability:

| Attribute | Production Value |
|---|---|
| **Base URL** | `https://buphackathon-production-ad62.up.railway.app` |
| **Interactive API Documentation** | [`https://buphackathon-production-ad62.up.railway.app/docs`](https://buphackathon-production-ad62.up.railway.app/docs) |
| **OpenAPI 3.1 Specification** | [`https://buphackathon-production-ad62.up.railway.app/openapi.json`](https://buphackathon-production-ad62.up.railway.app/openapi.json) |
| **Health Probe Endpoint** | `GET https://buphackathon-production-ad62.up.railway.app/health` |
| **Optimization Service Endpoint** | `POST https://buphackathon-production-ad62.up.railway.app/optimize-energy` |

---

## System Architecture & Pipeline

```text
                           [ Client Ingestion ]
                                    │
                                    ▼  FastAPI HTTP Request (POST /optimize-energy)
             ┌──────────────────────────────────────────────┐
             │ Stage 1: Pydantic v2 Schema & Type Assertion │
             └──────────────────────┬───────────────────────┘
                                    │ Validated Request Payload
                                    ▼
             ┌──────────────────────────────────────────────┐
             │ Stage 2: Constrained LLM Language Parsing    │
             │   (Google GenAI Gemini · Structured Output)  │
             └──────────────────────┬───────────────────────┘
                                    │ Raw JSON Candidate Directives
                                    ▼
             ┌──────────────────────────────────────────────┐
             │ Stage 3: Deterministic Guardrails Subsystem  │
             │  (Temporal Intervals · Numerical Invariants) │
             └──────────────────────┬───────────────────────┘
                                    │ Canonical Validated Directives
                                    ▼
             ┌──────────────────────────────────────────────┐
             │ Stage 4: Mathematical Optimization Engine    │
             │     (PuLP MILP Model + COIN-OR CBC Solver)   │
             └──────────────────────┬───────────────────────┘
                                    │ 24-Hour Dispatch Schedule
                                    ▼
             ┌──────────────────────────────────────────────┐
             │ Stage 5: Independent Schedule Validator      │
             │   (Physics Simulation & Fiscal Recalculation)│
             └──────────────────────┬───────────────────────┘
                                    │ Verified Financial & Physical Totals
                                    ▼
             ┌──────────────────────────────────────────────┐
             │ Stage 6: Response Assembly & Audit Envelope  │
             └──────────────────────────────────────────────┘
```

### Module Responsibilities

1. **Request Validation (`app.schemas`)**:
   Enforces strict structural constraints (exactly 24 chronological hours spanning indices `0..23`, 1–3 non-blank operator notes, battery physical parameters, and non-negative finite numerical values). Rejects extraneous parameters (`extra="forbid"`).
2. **LLM Language Interpreter (`app.llm_interpreter`)**:
   Translates free-form textual descriptions (e.g., *"Facilities will wash rooftop panels from noon until 2 PM"*) into formal candidate directive schemas.
   * **Domain Boundary**: The language model is exclusively tasked with semantic entity extraction and temporal reasoning. It does not calculate energy dispatch figures, modify electricity tariff schedules, or compute financial totals.
3. **Deterministic Guardrails (`app.guardrails`)**:
   A deterministic verification layer that intercepts the LLM output. Validates directive types against the official enumerations, checks factor boundaries ($0.0 \le \text{factor} \le 1.0$), verifies battery reserve capacity against hardware limits, guarantees temporal index monotonicity, and enforces start-inclusive/end-exclusive interval semantics.
4. **MILP Mathematical Optimizer (`app.optimizer`)**:
   Formulates and solves a 24-hour cost-minimization optimization problem using the COIN-OR Branch-and-Cut (CBC) solver.
5. **Independent Physics Validator (`app.validator`)**:
   Simulates the 24-hour physical microgrid operation step-by-step from $t=0$ to $t=23$. Independently verifies power conservation, battery capacity limits, rate constraints, and directive compliance without relying on solver state, recalculating verified fiscal and grid totals.

---

## Mathematical Formulation

The core dispatch problem is formulated as a Mixed-Integer Linear Program (MILP) over a 24-hour planning horizon $\mathcal{T} = \{0, 1, \dots, 23\}$ with discrete 1-hour time intervals ($\Delta t = 1.0\text{ h}$).

### Objective Function

Minimize the total electricity import procurement cost from the utility grid across the 24-hour horizon:

$$\min \sum_{t=0}^{23} P_{\text{grid}}[t] \times C_{\text{tariff}}[t]$$

Where:
* $P_{\text{grid}}[t] \ge 0$: Grid power imported during hour $t$ (kWh).
* $C_{\text{tariff}}[t] > 0$: Time-of-use tariff rate during hour $t$ (BDT/kWh).

### Physical & Operational Constraints

1. **Hourly Electrical Power Balance**:
   For every hour $t \in \mathcal{T}$, microgrid load demand must be met exactly:
   $$P_{\text{demand}}[t] = P_{\text{grid}}[t] + P_{\text{solar,used}}[t] + P_{\text{discharge}}[t] - P_{\text{charge}}[t]$$

2. **Solar PV Utilization & Curtailment**:
   Usable solar power cannot exceed the adjusted forecast:
   $$0 \le P_{\text{solar,used}}[t] \le P_{\text{solar}}[t] \times \alpha[t]$$
   Where $\alpha[t] \in [0.0, 1.0]$ represents the effective solar factor derived from directives (defaulting to $1.0$).

3. **Battery Energy Storage Dynamics**:
   Battery energy at the conclusion of hour $t$:
   $$E_{\text{battery}}[t] = \begin{cases} 
   E_{\text{initial}} + P_{\text{charge}}[0] - P_{\text{discharge}}[0], & t = 0 \\
   E_{\text{battery}}[t-1] + P_{\text{charge}}[t] - P_{\text{discharge}}[t], & 1 \le t \le 23 
   \end{cases}$$

4. **Charge and Discharge Mutual Exclusion**:
   To prevent non-physical simultaneous charging and discharging within the same time interval:
   $$0 \le P_{\text{charge}}[t] \le R_{\text{charge}}^{\max} \times u_{\text{charge}}[t]$$
   $$0 \le P_{\text{discharge}}[t] \le R_{\text{discharge}}^{\max} \times u_{\text{discharge}}[t]$$
   $$u_{\text{charge}}[t] + u_{\text{discharge}}[t] \le 1, \quad u_{\text{charge}}[t], u_{\text{discharge}}[t] \in \{0, 1\}$$

5. **Battery State of Charge Bounds**:
   For each hour $t \in \mathcal{T}$:
   $$E_{\min}[t] \le E_{\text{battery}}[t] \le E_{\text{capacity}}$$
   Where $E_{\min}[t] = \max(E_{\text{base,min}}, E_{\text{reserve}}[t])$.

6. **End-of-Day Neutrality Condition**:
   At the conclusion of the 24-hour dispatch cycle ($t = 23$), the battery energy level must strictly restore to its initial baseline value within standard numerical tolerance:
   $$\left| E_{\text{battery}}[23] - E_{\text{initial}} \right| \le 0.01\text{ kWh}$$

---

## Canonical Operational Directives

GridWise strictly supports six canonical directive types:

| Directive Type | Mathematical Semantic | JSON Adjustment Structure |
|---|---|---|
| `solar_reduction` | $P_{\text{solar,effective}}[t] = P_{\text{solar}}[t] \times \text{factor}$ | `{"hours": [int], "factor": float}` |
| `minimum_battery_reserve` | $E_{\text{battery}}[t] \ge \max(E_{\min}, E_{\text{reserve}})$ | `{"hours": [int], "minimum_energy_kwh": float}` |
| `no_charge_window` | $P_{\text{charge}}[t] = 0 \quad (\text{action} \neq \text{"charge"})$ | `{"hours": [int]}` |
| `no_discharge_window` | $P_{\text{discharge}}[t] = 0 \quad (\text{action} \neq \text{"discharge"})$ | `{"hours": [int]}` |
| `max_grid_window` | $P_{\text{grid}}[t] \le P_{\text{grid}}^{\max}$ | `{"hours": [int], "max_grid_kwh": float}` |
| `no_op` | Irrelevant operational note; no mathematical impact | `null` (`applies: false`) |

*All temporal windows follow 0-indexed, start-inclusive, end-exclusive representations (e.g., "1 PM to 3 PM" corresponds strictly to hours `[13, 14]`).*

---

## Configuration Reference

Application configuration is declared in `app/config.py` and sourced via environment variables or `.env`:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | String | `""` | Primary API credential for Google GenAI (aliases `GEMINI_API_KEY`) |
| `LLM_MODEL` | String | `gemini-3.1-flash-lite` | Foundation model identifier |
| `LLM_BASE_URL` | String | `""` | Custom provider endpoint if routing through a proxy |
| `LLM_TIMEOUT_SECONDS` | Float | `25.0` | Provider invocation timeout threshold in seconds |
| `PORT` | Integer | `8000` | HTTP application port |
| `LOG_LEVEL` | String | `"INFO"` | Standard logging output level |

---

## Installation & Local Development

### System Requirements
* Python 3.10 or higher
* COIN-OR CBC MILP Solver (`coinor-cbc`)

### Installation Steps

```bash
# 1. Clone repository
git clone https://github.com/Rushu41/BUP_HACKATHON.git
cd BUP_HACKATHON

# 2. Provision and activate a dedicated virtual environment
python -m venv venv

# On Linux / macOS:
source venv/bin/activate
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1

# 3. Install required Python packages
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure environment credentials
cp .env.example .env
# Populate .env with your LLM_API_KEY
```

### Local Execution

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
The service initializes and begins accepting HTTP connections at `http://localhost:8000`.

---

## API Verification & Usage

### 1. Health Probe (`GET /health`)

```bash
# Production
curl -s -X GET "https://buphackathon-production-ad62.up.railway.app/health"

# Local
curl -s -X GET "http://localhost:8000/health"
```

**Response (HTTP 200 OK)**:
```json
{
  "status": "ok"
}
```

### 2. Energy Optimization (`POST /optimize-energy`)

```bash
curl -s -X POST "https://buphackathon-production-ad62.up.railway.app/optimize-energy" \
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
  }' | jq
```

**Response (HTTP 200 OK)**:
```json
{
  "scenario_id": "DEMO-01",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {
        "hours": [12, 13],
        "factor": 0.25
      },
      "explanation": "Panel washing restricts solar PV output to 25% of forecast between 12:00 PM and 2:00 PM."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "Sports office deadline notice has no impact on energy or battery operations."
    }
  ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_kwh": 40.0,
      "solar_used_kwh": 0.0,
      "battery_action": "discharge",
      "battery_kwh": 50.0,
      "battery_energy_after_kwh": 50.0
    }
  ],
  "total_grid_kwh": 2695.0,
  "total_cost_bdt": 38450.0,
  "peak_grid_kwh": 175.0,
  "plan_summary": "Applied 1 operating directive (solar reduction), optimized grid use across the 24-hour horizon, and restored battery to its initial energy level."
}
```

---

## Automated Test Suites

The codebase includes automated test suites covering unit assertions, guardrails, optimizer physics, error handling, and end-to-end integration:

```bash
# 1. Execute complete test suite (179 tests)
python -m pytest tests/

# 2. Run official public benchmark scenarios against live cloud deployment
python scripts/test_public_cases.py --remote

# 3. Run offline mock verification of official benchmark scenarios
python scripts/test_public_cases.py --mock

# 4. Execute live backend diagnostic validation
python scripts/test_live_backend.py
```

---

## Containerized Deployment

A production-ready `Dockerfile` is provided for containerized environments:

```bash
# Build Docker image
docker build -t gridwise:latest .

# Run containerized service
docker run -d \
  -p 8000:8000 \
  -e LLM_API_KEY="your-api-key" \
  -e LLM_MODEL="gemini-3.1-flash-lite" \
  --name gridwise-service \
  gridwise:latest

# Verify container liveness
curl -s http://localhost:8000/health
```

---

## Security, Confidentiality & Compliance

1. **Zero Secret Leakage**:
   All credentials, environment templates, and provider tokens are strictly filtered out of version control and Docker images via `.gitignore` and `.dockerignore`.
2. **Sanitized Exception Handling**:
   Custom exception handlers sanitize all validation and runtime errors. Internal tracebacks and authorization tokens are never leaked to API clients.
3. **Formal Error Code Taxonomies**:
   Known exception events produce structured domain error objects (`REQUEST_VALIDATION_ERROR`, `GUARDRAIL_VALIDATION_ERROR`, `OPTIMIZATION_ERROR`, `PLAN_VALIDATION_ERROR`, `PROVIDER_ERROR`, `INTERNAL_SERVER_ERROR`).
