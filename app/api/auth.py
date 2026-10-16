"""Connexion par identifiant / mot de passe : delivre le jeton JWT."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.security.auth import Principal, create_access_token
from app.security.deps import client_ip, get_principal

router = APIRouter(prefix="/auth", tags=["Authentification"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    username: str
    display_name: str
    role: str
    tenant_id: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    state = request.app.state
    rid = uuid.uuid4().hex
    ip = client_ip(request)
    cle = f"{ip}:{body.username.lower()}"

    # Anti force brute : par couple (adresse, identifiant) puis par adresse seule.
    if not (state.login_limiter.allow(cle) and state.ip_limiter.allow(str(ip))):
        state.audit.record("RATE_LIMITED", rid, detail="login", client_ip=ip)
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Reessayez dans une minute.",
            headers={"Retry-After": str(max(state.login_limiter.retry_after(cle), 1))},
        )

    user = state.users.authenticate(body.username, body.password)

    if user is None:
        # Message identique que l'identifiant existe ou non.
        state.audit.record("AUTH_FAILED", rid, detail=f"login refuse ({body.username[:64]})",
                           client_ip=ip)
        raise HTTPException(status_code=401, detail="Identifiants invalides.")

    jeton = create_access_token(user.username, user.tenant_id, user.role,
                                settings.SECRET_KEY, settings.JWT_TTL_MINUTES)
    state.audit.record("LOGIN", rid, tenant_id=user.tenant_id, user_id=user.username,
                       role=user.role, client_ip=ip)

    return LoginResponse(
        access_token=jeton,
        expires_in=settings.JWT_TTL_MINUTES * 60,
        user=UserOut(username=user.username, display_name=user.display_name,
                     role=user.role, tenant_id=user.tenant_id),
    )


@router.get("/me", response_model=UserOut)
def me(request: Request, principal: Principal = Depends(get_principal)) -> UserOut:
    compte: Optional[object] = request.app.state.users.get(principal.user_id)
    return UserOut(
        username=principal.user_id,
        display_name=compte.display_name if compte else principal.user_id,
        role=principal.role,
        tenant_id=principal.tenant_id,
    )
