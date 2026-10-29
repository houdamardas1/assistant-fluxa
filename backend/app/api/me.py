"""Donnees personnelles de l'utilisateur connecte (jamais celles d'un autre)."""

from fastapi import APIRouter, Depends, Request

from app.security.auth import Principal
from app.security.deps import get_principal

router = APIRouter(prefix="/me", tags=["Utilisateur"])


@router.get("/history")
def history(request: Request, limit: int = 30,
            principal: Principal = Depends(get_principal)):
    """Ses propres questions/reponses (extraites du journal d'audit)."""
    return request.app.state.audit.user_history(
        principal.tenant_id, principal.user_id, limit
    )
