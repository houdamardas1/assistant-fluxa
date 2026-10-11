
# syntax=docker/dockerfile:1
FROM python:3.11-slim

LABEL maintainer="ABA"
LABEL description="Morocco Enterprise Intelligence Platform"

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ENVIRONMENT=production

WORKDIR /app

# System dependencies (faiss, sentence-transformers, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (Docker cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY rag/ ./rag/
COPY assistant.py .

# Create directories for SQLite audit
RUN mkdir -p data/eval && touch data/audit.db

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# uvicorn must listen on 0.0.0.0 in a container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]