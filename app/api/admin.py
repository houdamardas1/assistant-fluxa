"""Supervision : lecture du journal d'audit, limitee au tenant de l'appelant."""

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


@router.get("/audit/summary")
def audit_summary(request: Request, principal: Principal = Depends(get_principal)):
    _exiger_direction(request, principal)
    audit = request.app.state.audit
    return {
        "tenant_id": principal.tenant_id,
        "counts": audit.counts(tenant_id=principal.tenant_id),
    }


@router.get("/audit/recent")
def audit_recent(
    request: Request, limit: int = 50, principal: Principal = Depends(get_principal)
):
    _exiger_direction(request, principal)
    return request.app.state.audit.recent(limit, tenant_id=principal.tenant_id)
