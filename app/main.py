"""
Morocco Enterprise Intelligence Platform - Main Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Importer les routes
from app.api import documents

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Morocco Enterprise Intelligence Platform",
    description="Enterprise AI Platform for Moroccan Economic Data",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclure les routes
app.include_router(documents.router)

@app.get("/")
async def root():
    return {
        "service": "Morocco Enterprise Intelligence Platform",
        "version": "1.0.0",
        "status": "healthy",
        "endpoints": [
            "/",
            "/health",
            "/documents",
            "/documents/{company}",
            "/documents/{company}/chunks",
            "/docs"
        ]
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "documents_indexed": 4,
        "companies": ["Wafa Assurance", "CDG Capital", "Unimer", "Auto Nejma"],
        "total_pages": 487,
        "total_chunks": 165
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
