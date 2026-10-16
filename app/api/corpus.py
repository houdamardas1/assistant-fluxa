"""Statistiques reelles du corpus, limitees a ce que le role peut lire."""

from fastapi import APIRouter, Depends, Request

from app.security.auth import Principal
from app.security.deps import get_principal
from app.services.corpus import corpus_stats

router = APIRouter(prefix="/corpus", tags=["Corpus"])


@router.get("/stats")
def stats(request: Request, principal: Principal = Depends(get_principal)):
    from rag.rbac import departements_du_chunk, est_accessible

    return corpus_stats(
        request.app.state.rag.metadata, principal.role,
        est_accessible, departements_du_chunk,
    )
