"""
Journal d'audit (SQLite, stdlib). Meme schema que celui prevu pour PostgreSQL :
la migration ne changera que la connexion.

Evenements : ACCESS_GRANTED, ACCESS_DENIED, NO_ANSWER, CLARIFICATION_REQUESTED,
AUTH_FAILED, RATE_LIMITED, QUOTA_ERROR, ERROR, ADMIN_DENIED.

record() ne leve JAMAIS : une panne d'audit est journalisee (logging) mais ne
bloque pas la reponse (choix de POC ; en production, decider fail-open ou
fail-closed selon l'exigence de tracabilite).
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    request_id    TEXT NOT NULL,
    tenant_id     TEXT,
    user_id       TEXT,
    role          TEXT,
    event_type    TEXT NOT NULL,
    question      TEXT,
    mode          TEXT,
    departement   TEXT,
    sources       TEXT,
    confidence    REAL,
    latency_ms    INTEGER,
    answer_excerpt TEXT,
    detail        TEXT,
    client_ip     TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_event ON audit_log (tenant_id, event_type, ts);
"""

_MAX_TEXTE = 2000


def _tronque(texte: Optional[str]) -> Optional[str]:
    return None if texte is None else str(texte)[:_MAX_TEXTE]


class AuditLog:
    def __init__(self, path: str):
        self.path = str(path)
        self._lock = threading.Lock()
        try:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with self._connexion() as cx:
                cx.executescript(_SCHEMA)
        except Exception:
            logger.exception("Audit : initialisation impossible (%s)", self.path)

    @contextmanager
    def _connexion(self):
        """Connexion qui valide (commit) puis se FERME a la sortie : le
        context manager natif de sqlite3 ne ferme pas la connexion."""
        cx = sqlite3.connect(self.path, timeout=5)
        cx.row_factory = sqlite3.Row
        try:
            with cx:
                yield cx
        finally:
            cx.close()

    def record(
        self,
        event_type: str,
        request_id: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        question: Optional[str] = None,
        mode: Optional[str] = None,
        departement: Optional[str] = None,
        sources: Optional[list] = None,
        confidence: Optional[float] = None,
        latency_ms: Optional[int] = None,
        answer: Optional[str] = None,
        detail: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> bool:
        try:
            with self._lock, self._connexion() as cx:
                cx.execute(
                    "INSERT INTO audit_log (ts, request_id, tenant_id, user_id, role, "
                    "event_type, question, mode, departement, sources, confidence, "
                    "latency_ms, answer_excerpt, detail, client_ip) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                        request_id, tenant_id, user_id, role, event_type,
                        _tronque(question), mode, departement,
                        json.dumps(sources, ensure_ascii=False) if sources is not None else None,
                        confidence, latency_ms, _tronque(answer), _tronque(detail),
                        client_ip,
                    ),
                )
            return True
        except Exception:
            logger.exception("Audit : ecriture impossible (event=%s)", event_type)
            return False

    def counts(self, tenant_id: Optional[str] = None, since: Optional[str] = None) -> dict:
        sql = "SELECT event_type, COUNT(*) AS n FROM audit_log WHERE 1=1"
        params: list = []
        if tenant_id is not None:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        sql += " GROUP BY event_type ORDER BY event_type"
        with self._connexion() as cx:
            return {r["event_type"]: r["n"] for r in cx.execute(sql, params)}

    def recent(self, limit: int = 50, tenant_id: Optional[str] = None) -> list:
        limit = max(1, min(int(limit), 200))
        sql = "SELECT * FROM audit_log"
        params: list = []
        if tenant_id is not None:
            sql += " WHERE tenant_id = ?"
            params.append(tenant_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connexion() as cx:
            return [dict(r) for r in cx.execute(sql, params)]
