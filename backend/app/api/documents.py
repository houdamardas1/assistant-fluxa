"""
API endpoints pour les documents

SECURISE : authentification obligatoire et controle RBAC par entreprise
(rag.config.RBAC_POLICY). Refus par defaut : une entreprise absente de la
politique est interdite. Une entreprise non autorisee renvoie 404, comme une
entreprise inexistante (pas de fuite d'existence).
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.security.auth import Principal
from app.security.deps import get_principal
from rag.config import RBAC_POLICY

router = APIRouter(prefix="/documents", tags=["Documents"])


def _cle(nom: str) -> str:
    """'Wafa Assurance', 'wafa_assurance' et 'Wafa-Assurance' -> 'wafaassurance'."""
    return re.sub(r"[\s_\-]+", "", nom or "").lower()


def _entreprise_autorisee(company: str, role: str) -> bool:
    cible = _cle(company)
    for nom, roles in RBAC_POLICY.items():
        if _cle(nom) == cible:
            return role in roles
    return False


@router.get("/")
async def list_documents(
    principal: Principal = Depends(get_principal),
) -> List[Dict[str, Any]]:
    """Lister les documents indexés accessibles au role de l'appelant"""
    documents = []
    chunks_dir = Path("data/raw")

    for chunks_file in chunks_dir.glob("**/*_chunks.json"):
        try:
            with open(chunks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not _entreprise_autorisee(data.get("company", ""), principal.role):
                    continue
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
async def get_document(
    company: str, principal: Principal = Depends(get_principal)
) -> Dict[str, Any]:
    """Récupérer un document par entreprise"""
    chunks_dir = Path("data/raw")

    if _entreprise_autorisee(company, principal.role):
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
async def get_chunks(
    company: str, limit: int = 10, principal: Principal = Depends(get_principal)
) -> List[str]:
    """Récupérer les chunks d'un document"""
    chunks_dir = Path("data/raw")
    limit = max(1, min(limit, 100))

    if _entreprise_autorisee(company, principal.role):
        for chunks_file in chunks_dir.glob("**/*_chunks.json"):
            try:
                with open(chunks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("company", "").lower() == company.lower():
                        return data.get("chunks", [])[:limit]
            except Exception as e:
                print(f"Erreur lecture {chunks_file}: {e}")

    raise HTTPException(status_code=404, detail=f"Chunks pour {company} non trouvés")
