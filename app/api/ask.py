"""POST /ask : question a l'assistant, avec controle d'acces et audit."""

import logging
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.security.auth import Principal
from app.security.deps import client_ip, get_principal
from app.services.rag_service import event_for_mode, to_public
from rag.llm import QuotaError
from rag.messages import MESSAGE_QUOTA

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Assistant"])


class AskRequest(BaseModel):
    # Seul champ accepte : le role et le tenant viennent du jeton.
    question: str = Field(..., min_length=3, max_length=1000)


class Source(BaseModel):
    n: int
    fichier: Optional[str] = None
    page: Optional[int] = None
    entreprise: Optional[str] = None
    type: Optional[str] = None
    demo: bool = False
    verifie: bool = False


class AskResponse(BaseModel):
    request_id: str
    answer: str
    mode: str
    departement: Optional[str] = None
    confidence: float
    sources: List[Source]


@router.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> AskResponse:
    # `def` (et non `async def`) : le pipeline est bloquant (Groq, embeddings),
    # FastAPI l'execute dans un pool de threads.
    state = request.app.state
    rid = uuid.uuid4().hex
    ip = client_ip(request)
    qui = dict(tenant_id=principal.tenant_id, user_id=principal.user_id,
               role=principal.role, client_ip=ip)

    cle = f"{principal.tenant_id}:{principal.user_id}"
    if not state.limiter.allow(cle):
        state.audit.record("RATE_LIMITED", rid, question=body.question, **qui)
        raise HTTPException(
            status_code=429,
            detail="Trop de requetes. Reessayez dans un instant.",
            headers={"Retry-After": str(state.limiter.retry_after(cle))},
        )

    debut = time.perf_counter()

    try:
        resultat = state.rag.ask(body.question, principal.role)
    except QuotaError:
        state.audit.record("QUOTA_ERROR", rid, question=body.question, **qui)
        raise HTTPException(status_code=503, detail=MESSAGE_QUOTA.replace("\n\n", " - "))
    except Exception:
        logger.exception("Erreur pipeline (request_id=%s)", rid)
        state.audit.record("ERROR", rid, question=body.question, detail="exception pipeline", **qui)
        raise HTTPException(status_code=500, detail=f"Erreur interne (reference {rid}).")

    latence_ms = int((time.perf_counter() - debut) * 1000)
    public = to_public(resultat)

    state.audit.record(
        event_for_mode(public["mode"]), rid,
        question=body.question, mode=public["mode"],
        departement=public["departement"], sources=public["sources"],
        confidence=public["confidence"], latency_ms=latence_ms,
        answer=public["answer"],
        fondement=(resultat.get("fondement") or {}).get("score"), **qui,
    )

    return AskResponse(request_id=rid, **public)
