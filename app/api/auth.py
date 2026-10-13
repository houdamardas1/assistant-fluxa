"""
Routes d'authentification : generation de jeton JWT et info utilisateur.

ATTENTION : la route /auth/token est une route de DEMONSTRATION.
En production, il faudrait une vraie authentification (email + mot de passe
+ hash bcrypt + base de donnees users). Ici, n'importe qui peut demander
un jeton pour n'importe quel role.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.security.auth import create_access_token, Principal
from app.security.deps import get_principal


router = APIRouter(prefix="/auth", tags=["Auth"])


# Roles autorises (miroir de ROLES_DISPONIBLES cote rag.config).
ROLES_AUTORISES = (
    "tous", "finance", "direction", "it", "rh",
    "commerce", "juridique", "marketing",
)


class TokenRequest(BaseModel):
    role: str = Field(..., description="Role parmi ROLES_AUTORISES")
    tenant: str = Field(..., min_length=1, max_length=64)
    user: str = Field(..., min_length=1, max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant: str
    user: str


@router.post("/token", response_model=TokenResponse)
async def get_token(req: TokenRequest):
    """Genere un jeton JWT a partir d'un role, d'un tenant et d'un user.

    ATTENTION : pas de mot de passe. Route de DEMONSTRATION uniquement.
    """
    if req.role not in ROLES_AUTORISES:
        raise HTTPException(
            status_code=400,
            detail=f"Role inconnu. Disponibles : {list(ROLES_AUTORISES)}",
        )

    token = create_access_token(
        user_id=req.user,
        tenant_id=req.tenant,
        role=req.role,
        secret=settings.SECRET_KEY,
        ttl_minutes=settings.JWT_TTL_MINUTES,
    )

    return TokenResponse(
        access_token=token,
        role=req.role,
        tenant=req.tenant,
        user=req.user,
    )


@router.get("/me")
async def get_me(principal: Principal = Depends(get_principal)):
    """Retourne les informations du jeton courant.

    Permet au frontend de verifier qu'un jeton est encore valide.
    """
    return {
        "user": principal.user_id,
        "role": principal.role,
        "tenant": principal.tenant_id,
    }
