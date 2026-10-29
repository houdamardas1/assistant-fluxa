"""Dependances FastAPI : authentification par jeton Bearer."""

import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.security.auth import AuthError, Principal, decode_token
from rag.config import ROLES_DISPONIBLES

_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def get_principal(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Principal:
    """Identite issue du jeton. Le role n'est jamais lu ailleurs."""
    audit = request.app.state.audit
    rid = uuid.uuid4().hex
    entetes = {"WWW-Authenticate": "Bearer"}

    if creds is None:
        audit.record("AUTH_FAILED", rid, detail="jeton absent", client_ip=client_ip(request))
        raise HTTPException(status_code=401, detail="Authentification requise.", headers=entetes)

    try:
        return decode_token(creds.credentials, settings.SECRET_KEY, ROLES_DISPONIBLES)
    except AuthError as e:
        audit.record("AUTH_FAILED", rid, detail=str(e), client_ip=client_ip(request))
        # Message volontairement generique : ne dit pas pourquoi le jeton est refuse.
        raise HTTPException(status_code=401, detail="Jeton invalide ou expire.", headers=entetes)
