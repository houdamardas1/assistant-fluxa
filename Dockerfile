# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Métadonnées
LABEL maintainer="ABA"
LABEL description="Morocco Enterprise Intelligence Platform"

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ENVIRONMENT=production \
    WORKDIR=/app

# Répertoire de travail
WORKDIR ${WORKDIR}

# Dépendances système (faiss, sentence-transformers, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les requirements en premier (cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code applicatif
COPY app/ ./app/
COPY rag/ ./rag/
COPY assistant.py .

# Créer le dossier pour l'audit SQLite
RUN mkdir -p data/eval && touch data/audit.db

# Port exposé
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Point d'entrée : uvicorn doit écouter sur 0.0.0.0 dans un conteneur
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]