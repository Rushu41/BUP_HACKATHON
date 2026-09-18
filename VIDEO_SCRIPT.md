# GridWise Video Script (3 Minutes)

**0:00–0:20 | The Problem**
"Hello! Welcome to GridWise. Modern microgrids face a complex challenge: operators leave unstructured text notes—like 'Keep 20% battery reserve' or 'Solar falls to half'—that traditional schedulers can't understand. Our platform bridges the gap, translating human instructions into cost-saving, optimized energy schedules."

**0:20–0:45 | Architecture**
"GridWise is built on a highly modular architecture. Requests enter via our API, hit a language model interpreter, pass through strict deterministic guardrails, get converted into mathematical constraints, and are finally solved by our optimizer. Everything is independently validated before responding to the user."

**0:45–1:20 | LLM Interpretation**
"For interpretation, we leverage Gemini's structured output capabilities. Instead of fragile regex, the LLM maps sentences like 'Solar falls to 20% between 1 PM and 3 PM' strictly into one of six supported directives, handling paraphrasing effortlessly. We've instructed it never to invent values, meaning it distinguishes between a valid constraint and an irrelevant note, like 'The cafeteria menu changed'."

**1:20–1:45 | Deterministic Guardrails**
"Language models can hallucinate, which is why we built strict deterministic guardrails. After the LLM outputs a directive, our system checks every temporal bound, ensures factors are strictly between zero and one, and verifies reserves don't exceed battery capacity. If the LLM makes a mistake, we offer exactly one controlled retry with the exact error message, ensuring stability."

**1:45–2:15 | Mathematical Optimizer**
"With our constraints formalized safely, our mathematical optimizer takes over. It calculates the absolute cheapest battery charging and discharging cycles over 24 hours while respecting the operator's directives and physical battery limits, turning constraints into a mathematically optimal schedule."

**2:15–2:35 | Final Validator**
"Before the response goes back to the client, a final, independent validator reviews the optimizer's homework. It checks battery neutrality, verifies no physical limits were breached, and recalculates the total cost manually. Trust, but verify."

**2:35–2:50 | Public Sample Testing**
"To ensure absolute correctness, we run extensive automated testing. We created a dynamic test runner to process 10 official public scenarios, ensuring our integrations, prompt semantic robustness, and cost equivalences hold perfectly under real-world constraints."

**2:50–3:00 | Deployment**
"Deployment is simple and robust. Our unified Dockerfile packages the system efficiently without leaking any API keys or secrets. Run a single command, and GridWise is ready to optimize your grid. Thank you!"
