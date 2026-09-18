FROM python:3.10-slim

WORKDIR /app

# Expose the configurable port (default 8000 for FastAPI)
EXPOSE 8000

# Install dependencies (do not copy .env or bake in secrets)
# We expect a requirements.txt from the combined integration, but for now we install what LLM uses.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Startup command matches final FastAPI app. Assuming Developer 1 will create `app.main` with a FastAPI `app`
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
