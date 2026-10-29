"""
Authentification par jeton JWT (HS256), sans dependance FastAPI.

Le jeton porte l'identite ET le role : le role n'est JAMAIS lu dans le corps
d'une requete (un client ne peut pas s'attribuer un role).

Claims : sub (utilisateur), tenant_id, role, iat, exp.
"""

import time
from dataclasses import dataclass
from typing import Iterable, Optional

import jwt

ALGORITHM = "HS256"
LONGUEUR_MIN_SECRET = 32
PREFIXE_SECRET_PAR_DEFAUT = "your-secret-key"


class AuthError(Exception):
    """Jeton absent, invalide, expire ou incoherent."""


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    secret: str,
    ttl_minutes: int = 60,
    now: Optional[float] = None,
) -> str:
    emis = int(now if now is not None else time.time())
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": emis,
        "exp": emis + int(ttl_minutes) * 60,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str, allowed_roles: Iterable[str]) -> Principal:
    """Valide signature, expiration et claims. Leve AuthError sinon.

    L'algorithme est impose cote serveur (algorithms=[HS256]) : un jeton
    "alg: none" ou signe avec un autre algorithme est refuse."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise AuthError("jeton expire") from e
    except jwt.PyJWTError as e:
        raise AuthError("jeton invalide") from e

    user = payload.get("sub")
    tenant = payload.get("tenant_id")
    role = payload.get("role")

    if not isinstance(user, str) or not user:
        raise AuthError("claim sub manquant")
    if not isinstance(tenant, str) or not tenant:
        raise AuthError("claim tenant_id manquant")
    if role not in set(allowed_roles):
        raise AuthError("role inconnu")

    return Principal(user_id=user, tenant_id=tenant, role=role)


def check_secret(secret: str, environment: str) -> Optional[str]:
    """Controle la robustesse de SECRET_KEY.

    Hors environnement 'development' : leve RuntimeError (refus de demarrer).
    En developpement : retourne un message d'avertissement (ou None)."""
    problemes = []

    if (secret or "").startswith(PREFIXE_SECRET_PAR_DEFAUT):
        problemes.append("SECRET_KEY est la valeur par defaut du depot")
    if len(secret or "") < LONGUEUR_MIN_SECRET:
        problemes.append(f"SECRET_KEY fait moins de {LONGUEUR_MIN_SECRET} caracteres")

    if not problemes:
        return None

    message = "; ".join(problemes) + " : definir SECRET_KEY dans .env."

    if (environment or "").lower() != "development":
        raise RuntimeError(f"Configuration refusee ({environment}) : {message}")

    return message


class RateLimiter:
    """Fenetre glissante en memoire : max_calls par window_s et par cle.
    Suffisant pour un seul processus ; a remplacer par Redis en multi-instances."""

    def __init__(self, max_calls: int, window_s: float = 60.0, clock=time.monotonic):
        import threading
        from collections import defaultdict, deque

        self.max_calls = max_calls
        self.window_s = window_s
        self._clock = clock
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _purger(self, cle: str, maintenant: float) -> None:
        q = self._hits[cle]
        while q and maintenant - q[0] >= self.window_s:
            q.popleft()

    def allow(self, cle: str) -> bool:
        with self._lock:
            maintenant = self._clock()
            self._purger(cle, maintenant)
            q = self._hits[cle]
            if len(q) >= self.max_calls:
                return False
            q.append(maintenant)
            return True

    def retry_after(self, cle: str) -> int:
        with self._lock:
            maintenant = self._clock()
            self._purger(cle, maintenant)
            q = self._hits[cle]
            if len(q) < self.max_calls or not q:
                return 0
            return max(1, int(self.window_s - (maintenant - q[0])) + 1)
