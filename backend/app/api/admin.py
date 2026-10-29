"""Supervision : lecture du journal d'audit, limitee au tenant de l'appelant."""

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.security.auth import Principal
from app.security.deps import client_ip, get_principal

router = APIRouter(prefix="/admin", tags=["Admin"])


def _exiger_direction(request: Request, principal: Principal) -> None:
    if principal.role != "direction":
        request.app.state.audit.record(
            "ADMIN_DENIED", uuid.uuid4().hex, tenant_id=principal.tenant_id,
            user_id=principal.user_id, role=principal.role,
            detail=request.url.path, client_ip=client_ip(request),
        )
        raise HTTPException(status_code=403, detail="Acces reserve a la direction.")


def _usage(audit, tenant):
    """Tokens consommes et cout estime (prix en USD par million de tokens,
    fournis par LLM_PRICE_IN_PER_M / LLM_PRICE_OUT_PER_M ; sinon cout inconnu)."""
    u = audit.usage_stats(tenant)
    u["tokens_total"] = u["tokens_in"] + u["tokens_out"]
    u["avg_tokens"] = round(u["tokens_total"] / u["requests_llm"]) if u["requests_llm"] else None
    try:
        prix_in = float(os.getenv("LLM_PRICE_IN_PER_M", ""))
        prix_out = float(os.getenv("LLM_PRICE_OUT_PER_M", ""))
        u["cost_usd"] = round((u["tokens_in"] * prix_in + u["tokens_out"] * prix_out) / 1_000_000, 4)
    except ValueError:
        u["cost_usd"] = None
    return u


@router.get("/audit/summary")
def audit_summary(request: Request, principal: Principal = Depends(get_principal)):
    _exiger_direction(request, principal)
    audit, tenant = request.app.state.audit, principal.tenant_id
    return {
        "tenant_id": tenant,
        "counts": audit.counts(tenant_id=tenant),
        "latency": audit.latency_stats(tenant),
        "by_role": audit.counts_by_role(tenant),
        "usage": _usage(audit, tenant),
    }


@router.get("/audit/timeseries")
def audit_timeseries(request: Request, days: int = 14,
                     principal: Principal = Depends(get_principal)):
    _exiger_direction(request, principal)
    audit, tenant = request.app.state.audit, principal.tenant_id
    return {"tenant_id": tenant, "days": audit.timeseries(tenant, days)}


@router.get("/audit/recent")
def audit_recent(
    request: Request, limit: int = 50, principal: Principal = Depends(get_principal)
):
    _exiger_direction(request, principal)
    return request.app.state.audit.recent(limit, tenant_id=principal.tenant_id)
