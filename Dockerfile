# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache \
    ENVIRONMENT=production

WORKDIR /app

# curl is only needed by the healthcheck. Re-add build-essential here if a
# pip install ever fails because a wheel has to be compiled.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch: the default Linux wheel pulls several GB of CUDA libraries.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image: no download at container start.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
ENV HF_HUB_OFFLINE=1

COPY app/ ./app/
COPY rag/ ./rag/
COPY create_user.py ./

# Non-root user. data/ holds the audit database (volume) and the FAISS index
# (read-only bind mount): neither is copied into the image.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data/index /app/data/db \
    && chown -R appuser:appuser /app /opt/hf-cache
USER appuser

EXPOSE 8000

# Loading torch + faiss + the model takes about a minute.
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
