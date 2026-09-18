import json
import asyncio
import sys
import os
from app.llm_interpreter import interpret_operator_notes

async def main():
    json_path = os.path.join(os.path.dirname(__file__), "..", "public_cases.json")
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found")
        sys.exit(1)
        
    with open(json_path, 'r') as f:
        cases = json.load(f)
        
    print(f"Loaded {len(cases)} public cases")
    
    # Check if GEMINI_API_KEY is set, if not mock the response for demonstration
    use_mock = not os.environ.get("GEMINI_API_KEY")
    if use_mock:
        print("GEMINI_API_KEY not set. Using mock mode for demonstration.")
        from unittest.mock import patch
        
    for case in cases:
        print(f"\n--- Running case {case['scenario_id']} ---")
        operator_notes = case.get("operator_notes", [])
        battery = case.get("battery", {})
        hours = case.get("hours", [])
        
        try:
            if use_mock:
                # Mock a successful response matching expected
                mock_response = json.dumps(case.get("expected_directives", []))
                with patch("app.llm_interpreter.call_llm", return_value=mock_response):
                    interpretations = await interpret_operator_notes(operator_notes, battery, hours)
            else:
                interpretations = await interpret_operator_notes(operator_notes, battery, hours)
                
            print("Interpretations:")
            print(json.dumps(interpretations, indent=2))
            
            # Here we would normally plug into the optimizer/validator, but that's Dev 1/2's job.
            # We just print the valid interpretations.
        except Exception as e:
            print(f"Error in {case['scenario_id']}: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
