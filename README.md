# GridWise
**BUP CSE Fest 2026**

## Challenge Overview
GridWise is a robust energy scheduling platform. It combines language-based operator notes, strict deterministic guardrails, and a mathematical optimizer to produce a 24-hour battery and grid utilization plan that is valid, safe, and optimally cost-effective.

## Architecture
The application flow processes requests in stages:
1. **Request** → Validated against API schemas
2. **LLM Interpreter** → Converts unstructured operator notes to proposed JSON directives
3. **Deterministic Guardrails** → Strict bounds and schema checking on LLM output
4. **Directive Application** → Converts schedule intents to optimization bounds
5. **Mathematical Optimizer** → Solves for the cheapest 24-hour schedule
6. **Final Validator** → Independently verifies the result
7. **Response** → Returns the total cost and full energy schedule

### LLM Role & Provider
- **Provider**: Google GenAI (Gemini 2.5 Flash)
- **Role**: Converting operator notes into standardized objects using provider structured output capabilities.
- **Limitations**: The LLM is restricted strictly to interpretation. It cannot invent values, cannot modify the energy schedule directly, and is actively prevented from producing unsupported directives by the guardrails.

### Guardrails
Strict guardrails run deterministically after the LLM:
- Reject any missing/duplicate indices or notes
- Reject unexpected directive types
- Check bounds (e.g. fraction factor `0..1`, reserve <= battery capacity)
- Validate temporal rules (hours `0..23`, unique, sorted)
- Allows **1-time recovery retry** if the first LLM generation fails the check.

### Supported Directives
- `solar_reduction`
- `minimum_battery_reserve`
- `no_charge_window`
- `no_discharge_window`
- `max_grid_window`
- `no_op`

### Optimizer/Solver
A mathematical optimizer takes the guardrail-validated schedule directives and produces a cost-minimal 24-hour schedule honoring physical battery limitations, time-of-use tariffs, and solar generation.

---

## Environment Variables
- `GEMINI_API_KEY`: Required for LLM integration. (Ensure this is not logged or committed)

## Installation & Running Locally

1. Create virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # Or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

2. Export the LLM API key:
```bash
export GEMINI_API_KEY="your-api-key"
```

3. **Exact local run command** *(Awaiting final merge verification)*:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Testing Commands

**Unit Tests**:
```bash
python -m pytest tests/
```

**Live LLM Integration Test Command** *(Requires API Key)*:
```bash
export GEMINI_API_KEY="your-api-key"
python -m pytest tests/test_public_cases.py
```

**Public Sample Test Command** *(Standalone runner)*:
```bash
python scripts/test_public_cases.py
```

## Docker

**Build**:
```bash
docker build -t gridwise-app .
```

**Run**:
```bash
docker run -p 8000:8000 -e GEMINI_API_KEY="your-key" gridwise-app
```

**Health Test** *(Awaiting merge verification)*:
```bash
curl http://localhost:8000/health
```

## Example API Requests *(Awaiting final merge)*

**GET /health**:
```bash
curl http://localhost:8000/health
```

**POST /optimize-energy**:
```bash
curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{ "scenario_id": "...", "operator_notes": ["..."], "hours": [...], "battery": {...} }'
```

## Dependencies & Security
- **Dependencies**: `google-genai`, `pytest`, `pytest-asyncio`, `fastapi`, `uvicorn` (See `requirements.txt`)
- **Security**: Strict prevention of secret logging. SDK exceptions and guardrail failures are safely abstracted as 422 HTTP responses. No internal traces are exposed.

## Known Limitations
- The interpreter LLM requires internet access to reach the provider APIs.
- The 1-time recovery adds latency on adversarial inputs, but guarantees deterministic bounds safely.
