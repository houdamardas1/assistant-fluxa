"""
Comptes utilisateurs (SQLite) avec mots de passe haches par scrypt (stdlib).

Aucun mot de passe en clair, aucune dependance externe. Le format stocke est
auto-descriptif ("scrypt$n$r$p$sel$hash") : les parametres pourront etre
durcis plus tard sans casser les comptes existants.
"""

import base64
import hashlib
import hmac
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 32
_MAXMEM = 64 * 1024 * 1024

MIN_PASSWORD = 10
MAX_PASSWORD = 128

_RE_USER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{2,63}$")
_RE_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _b64(octets: bytes) -> str:
    return base64.b64encode(octets).decode("ascii")


def hash_password(password: str, *, salt: Optional[bytes] = None,
                  n: int = _N, r: int = _R, p: int = _P) -> str:
    salt = salt if salt is not None else os.urandom(16)
    cle = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                         dklen=_DKLEN, maxmem=_MAXMEM)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(cle)}"


def verify_password(password: str, stored: str) -> bool:
    """Comparaison a temps constant. Ne leve jamais : un hash illisible = faux."""
    try:
        schema, n, r, p, sel, attendu = stored.split("$")
        if schema != "scrypt":
            return False
        calcule = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(sel),
            n=int(n), r=int(r), p=int(p), dklen=_DKLEN, maxmem=_MAXMEM,
        )
        return hmac.compare_digest(calcule, base64.b64decode(attendu))
    except (ValueError, TypeError, AttributeError):
        return False


# Hash factice : verifie quand l'utilisateur n'existe pas, pour que le temps de
# reponse ne revele pas si un identifiant existe.
_DUMMY_HASH = hash_password("mot-de-passe-factice-pour-egaliser-les-temps")


@dataclass(frozen=True)
class User:
    username: str
    display_name: str
    role: str
    tenant_id: str
    active: bool = True


class UserStore:
    def __init__(self, path: str, allowed_roles: Iterable[str]):
        self.path = str(path)
        self.allowed_roles = set(allowed_roles)
        self._lock = threading.Lock()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connexion() as cx:
            cx.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " username TEXT NOT NULL UNIQUE COLLATE NOCASE,"
                " password_hash TEXT NOT NULL,"
                " display_name TEXT NOT NULL,"
                " role TEXT NOT NULL,"
                " tenant_id TEXT NOT NULL,"
                " active INTEGER NOT NULL DEFAULT 1,"
                " created_at TEXT NOT NULL)"
            )

    @contextmanager
    def _connexion(self):
        cx = sqlite3.connect(self.path, timeout=5)
        cx.row_factory = sqlite3.Row
        try:
            with cx:
                yield cx
        finally:
            cx.close()

    @staticmethod
    def _user(ligne: sqlite3.Row) -> User:
        return User(ligne["username"], ligne["display_name"], ligne["role"],
                    ligne["tenant_id"], bool(ligne["active"]))

    def create_user(self, username: str, password: str, role: str, tenant_id: str,
                    display_name: Optional[str] = None) -> User:
        if not _RE_USER.match(username or ""):
            raise ValueError("Identifiant invalide (3 a 64 caracteres : lettres, chiffres, . _ @ -).")
        if not _RE_TENANT.match(tenant_id or ""):
            raise ValueError("Tenant invalide (lettres, chiffres, . _ -).")
        if role not in self.allowed_roles:
            raise ValueError(f"Role inconnu : {role!r}.")
        if not (MIN_PASSWORD <= len(password or "") <= MAX_PASSWORD):
            raise ValueError(f"Mot de passe : entre {MIN_PASSWORD} et {MAX_PASSWORD} caracteres.")

        nom = (display_name or username).strip()[:80] or username
        try:
            with self._lock, self._connexion() as cx:
                cx.execute(
                    "INSERT INTO users (username, password_hash, display_name, role, "
                    "tenant_id, active, created_at) VALUES (?,?,?,?,?,1,?)",
                    (username, hash_password(password), nom, role, tenant_id,
                     datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError("Cet identifiant existe deja.") from e
        return User(username, nom, role, tenant_id, True)

    def authenticate(self, username: str, password: str) -> Optional[User]:
        with self._connexion() as cx:
            ligne = cx.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if ligne is None:
            verify_password(password, _DUMMY_HASH)     # egalise le temps de reponse
            return None

        bon = verify_password(password, ligne["password_hash"])
        if not bon or not ligne["active"]:
            return None
        return self._user(ligne)

    def get(self, username: str) -> Optional[User]:
        with self._connexion() as cx:
            ligne = cx.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return self._user(ligne) if ligne else None

    def list_users(self) -> List[User]:
        with self._connexion() as cx:
            return [self._user(r) for r in cx.execute("SELECT * FROM users ORDER BY username")]

    def set_active(self, username: str, active: bool) -> bool:
        with self._lock, self._connexion() as cx:
            return cx.execute("UPDATE users SET active = ? WHERE username = ?",
                              (1 if active else 0, username)).rowcount > 0

    def set_password(self, username: str, password: str) -> bool:
        if not (MIN_PASSWORD <= len(password or "") <= MAX_PASSWORD):
            raise ValueError(f"Mot de passe : entre {MIN_PASSWORD} et {MAX_PASSWORD} caracteres.")
        with self._lock, self._connexion() as cx:
            return cx.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                              (hash_password(password), username)).rowcount > 0
