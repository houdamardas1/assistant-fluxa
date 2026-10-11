"""
API endpoints pour les documents
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import json
from pathlib import Path

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.get("/")
async def list_documents() -> List[Dict[str, Any]]:
    """Lister tous les documents indexés"""
    documents = []
    chunks_dir = Path("data/raw")
    
    for chunks_file in chunks_dir.glob("**/*_chunks.json"):
        try:
            with open(chunks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                documents.append({
                    "file_name": data.get("file_name"),
                    "company": data.get("company"),
                    "sector": data.get("sector"),
                    "total_pages": data.get("total_pages"),
                    "total_chunks": data.get("total_chunks")
                })
        except Exception as e:
            print(f"Erreur lecture {chunks_file}: {e}")
    
    return documents

@router.get("/{company}")
async def get_document(company: str) -> Dict[str, Any]:
    """Récupérer un document par entreprise"""
    chunks_dir = Path("data/raw")
    
    for chunks_file in chunks_dir.glob("**/*_chunks.json"):
        try:
            with open(chunks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("company", "").lower() == company.lower():
                    return data
        except Exception as e:
            print(f"Erreur lecture {chunks_file}: {e}")
    
    raise HTTPException(status_code=404, detail=f"Document pour {company} non trouvé")

@router.get("/{company}/chunks")
async def get_chunks(company: str, limit: int = 10) -> List[str]:
    """Récupérer les chunks d'un document"""
    chunks_dir = Path("data/raw")
    
    for chunks_file in chunks_dir.glob("**/*_chunks.json"):
        try:
            with open(chunks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("company", "").lower() == company.lower():
                    return data.get("chunks", [])[:limit]
        except Exception as e:
            print(f"Erreur lecture {chunks_file}: {e}")
    
    raise HTTPException(status_code=404, detail=f"Chunks pour {company} non trouvés")
