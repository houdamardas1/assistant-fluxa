"""
Morocco Enterprise Intelligence Platform - Main Application
"""

import logging
from contextlib import asynccontextmanager
from typing import Callable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, ask, auth, documents
from app.core.config import settings
from app.security.auth import RateLimiter, check_secret
from app.services.audit import AuditLog
from app.services.rag_service import RagService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app(
    rag_factory: Optional[Callable[[], RagService]] = None,
    audit_path: Optional[str] = None,
) -> FastAPI:
    """Fabrique de l'application. Les parametres permettent d'injecter un
    faux service RAG et une base d'audit temporaire dans les tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Refuse de demarrer hors "development" avec une SECRET_KEY faible.
        avertissement = check_secret(settings.SECRET_KEY, settings.ENVIRONMENT)
        if avertissement:
            logger.warning(avertissement)

        app.state.audit = AuditLog(audit_path or settings.AUDIT_DB_PATH)
        app.state.limiter = RateLimiter(settings.RATE_LIMIT_PER_MINUTE)

        logger.info("Chargement de l'index et du modele d'embeddings...")
        app.state.rag = (rag_factory or RagService.from_disk)()
        logger.info("Pret : %s chunks.", app.state.rag.n_chunks)
        yield

    app = FastAPI(
        title="Morocco Enterprise Intelligence Platform",
        description="Enterprise AI Platform for Moroccan Economic Data",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS : origines explicites (jamais "*"), pas de cookies (jeton Bearer).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(ask.router)
    app.include_router(documents.router)
    app.include_router(admin.router)
    app.include_router(auth.router)

    @app.get("/")
    async def root():
        return {
            "service": "Morocco Enterprise Intelligence Platform",
            "version": "1.0.0",
            "status": "healthy",
        }

    @app.get("/health")
    async def health_check():
        # Aucune statistique en dur : seulement l'etat reel du service.
        return {
            "status": "healthy",
            "index_loaded": getattr(app.state, "rag", None) is not None,
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
