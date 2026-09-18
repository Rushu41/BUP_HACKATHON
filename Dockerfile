FROM python:3.10-slim

WORKDIR /app

# Install CBC solver and clean package caches
RUN apt-get update && \
    apt-get install -y --no-install-recommends coinor-cbc && \
    rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code (excluding items in .dockerignore)
COPY . .

# Default application port
ENV PORT=8000
EXPOSE 8000

# Start FastAPI service on 0.0.0.0 with configurable PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
