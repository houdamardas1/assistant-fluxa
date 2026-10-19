"""
Journal d'audit (SQLite, stdlib). Meme schema que celui prevu pour PostgreSQL :
la migration ne changera que la connexion.

Evenements : ACCESS_GRANTED, ACCESS_DENIED, NO_ANSWER, CLARIFICATION_REQUESTED,
LOGIN, AUTH_FAILED, RATE_LIMITED, QUOTA_ERROR, ERROR, ADMIN_DENIED, PROMPT_BLOCKED.

record() ne leve JAMAIS : une panne d'audit est journalisee (logging) mais ne
bloque pas la reponse (choix de POC ; en production, decider fail-open ou
fail-closed selon l'exigence de tracabilite).
"""

import json
import logging
import math
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # SQLite seul : psycopg facultatif
    psycopg = None
    dict_row = None

logger = logging.getLogger(__name__)

REQUETES = ("ACCESS_GRANTED", "ACCESS_DENIED", "NO_ANSWER", "CLARIFICATION_REQUESTED",
            "PROMPT_BLOCKED")
ERREURS = ("ERROR", "QUOTA_ERROR")

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
    fondement     REAL,
    latency_ms    INTEGER,
    answer_excerpt TEXT,
    detail        TEXT,
    client_ip     TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_event ON audit_log (tenant_id, event_type, ts);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log (tenant_id, user_id, id);
"""

_MAX_TEXTE = 2000


def _tronque(texte: Optional[str]) -> Optional[str]:
    return None if texte is None else str(texte)[:_MAX_TEXTE]


def _marques(valeurs) -> str:
    return ",".join("?" for _ in valeurs)


_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS audit_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
    confidence    DOUBLE PRECISION,
    fondement     DOUBLE PRECISION,
    latency_ms    INTEGER,
    answer_excerpt TEXT,
    detail        TEXT,
    client_ip     TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_event ON audit_log (tenant_id, event_type, ts);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log (tenant_id, user_id, id);
"""


class _CxPg:
    """Adapte une connexion psycopg a l'API utilisee ici (placeholders '?')."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        return self._raw.execute(sql.replace("?", "%s"), params or None)


class AuditLog:
    def __init__(self, path: str, database_url: Optional[str] = None):
        self.path = str(path)
        self.url = database_url or None
        self._pg = bool(self.url)
        self._lock = threading.Lock()
        if self._pg and psycopg is None:
            raise RuntimeError("DATABASE_URL defini mais psycopg n'est pas installe")
        try:
            if self._pg:
                with self._connexion() as cx:
                    cx.execute(_SCHEMA_PG)
                    cx.execute("ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS fondement DOUBLE PRECISION")
                    for col, typ in (("model", "TEXT"), ("tokens_in", "INTEGER"), ("tokens_out", "INTEGER")):
                        cx.execute(f"ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS {col} {typ}")
            else:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                with self._connexion() as cx:
                    cx.executescript(_SCHEMA)
                    cols = {r[1] for r in cx.execute("PRAGMA table_info(audit_log)")}
                    if "fondement" not in cols:
                        cx.execute("ALTER TABLE audit_log ADD COLUMN fondement REAL")
                    for col, typ in (("model", "TEXT"), ("tokens_in", "INTEGER"), ("tokens_out", "INTEGER")):
                        if col not in cols:
                            cx.execute(f"ALTER TABLE audit_log ADD COLUMN {col} {typ}")
        except Exception:
            logger.exception("Audit : initialisation impossible (%s)",
                             "PostgreSQL" if self._pg else self.path)

    @contextmanager
    def _connexion(self):
        """Connexion qui valide (commit) puis se FERME a la sortie : le
        context manager natif de sqlite3 ne ferme pas la connexion."""
        if self._pg:
            raw = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5)
            try:
                yield _CxPg(raw)
                raw.commit()
            except Exception:
                raw.rollback()
                raise
            finally:
                raw.close()
            return
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
        fondement: Optional[float] = None,
        model: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        answer: Optional[str] = None,
        detail: Optional[str] = None,
        client_ip: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> bool:
        try:
            with self._lock, self._connexion() as cx:
                cx.execute(
                    "INSERT INTO audit_log (ts, request_id, tenant_id, user_id, role, "
                    "event_type, question, mode, departement, sources, confidence, "
                    "latency_ms, answer_excerpt, detail, client_ip, fondement, "
                    "model, tokens_in, tokens_out) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        ts or datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                        request_id, tenant_id, user_id, role, event_type,
                        _tronque(question), mode, departement,
                        json.dumps(sources, ensure_ascii=False) if sources is not None else None,
                        confidence, latency_ms, _tronque(answer), _tronque(detail),
                        client_ip, fondement, model, tokens_in, tokens_out,
                    ),
                )
            return True
        except Exception:
            logger.exception("Audit : ecriture impossible (event=%s)", event_type)
            return False

    # ------------------------------------------------------------ lectures

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

    def counts_by_role(self, tenant_id: str, since: Optional[str] = None) -> dict:
        """Requetes (hors erreurs techniques) par role d'utilisateur."""
        sql = ("SELECT role, COUNT(*) AS n FROM audit_log WHERE tenant_id = ? "
               f"AND event_type IN ({_marques(REQUETES)})")
        params: list = [tenant_id, *REQUETES]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        sql += " GROUP BY role ORDER BY n DESC"
        with self._connexion() as cx:
            return {r["role"] or "(inconnu)": r["n"] for r in cx.execute(sql, params)}

    def timeseries(self, tenant_id: str, days: int = 14,
                   today: Optional[datetime] = None) -> list:
        """Une ligne par jour UTC (jours sans activite inclus, a zero)."""
        days = max(1, min(int(days), 90))
        fin = (today or datetime.now(timezone.utc)).date()
        debut = fin - timedelta(days=days - 1)

        with self._connexion() as cx:
            lignes = cx.execute(
                "SELECT substr(ts, 1, 10) AS jour, event_type, COUNT(*) AS n "
                "FROM audit_log WHERE tenant_id = ? AND ts >= ? "
                "GROUP BY jour, event_type",
                (tenant_id, debut.isoformat()),
            ).fetchall()

        par_jour: dict = {}
        for r in lignes:
            par_jour.setdefault(r["jour"], {})[r["event_type"]] = r["n"]

        serie = []
        for i in range(days):
            jour = (debut + timedelta(days=i)).isoformat()
            c = par_jour.get(jour, {})
            serie.append({
                "day": jour,
                "requests": sum(c.get(e, 0) for e in REQUETES),
                "granted": c.get("ACCESS_GRANTED", 0),
                "denied": c.get("ACCESS_DENIED", 0),
                "no_answer": c.get("NO_ANSWER", 0),
                "blocked": c.get("PROMPT_BLOCKED", 0),
                "errors": sum(c.get(e, 0) for e in ERREURS),
            })
        return serie

    def latency_stats(self, tenant_id: str, limit: int = 5000) -> dict:
        """Latences (ms) des requetes traitees : moyenne, mediane, p95."""
        with self._connexion() as cx:
            valeurs = sorted(r["latency_ms"] for r in cx.execute(
                "SELECT latency_ms FROM audit_log WHERE tenant_id = ? "
                "AND latency_ms IS NOT NULL ORDER BY id DESC LIMIT ?",
                (tenant_id, limit),
            ))
        n = len(valeurs)
        if n == 0:
            return {"n": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None}

        def rang(q: float) -> int:      # rang le plus proche (nearest-rank)
            return valeurs[max(0, math.ceil(q * n) - 1)]

        return {"n": n, "avg_ms": round(sum(valeurs) / n), "p50_ms": rang(0.5),
                "p95_ms": rang(0.95)}

    def usage_stats(self, tenant_id: str) -> dict:
        """Tokens consommes par les requetes ayant appele le modele."""
        with self._connexion() as cx:
            t = cx.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(tokens_in), 0) AS tin, "
                "COALESCE(SUM(tokens_out), 0) AS tout FROM audit_log "
                "WHERE tenant_id = ? AND tokens_in IS NOT NULL", (tenant_id,),
            ).fetchone()
            par_modele = {r["model"]: r["tok"] for r in cx.execute(
                "SELECT model, COALESCE(SUM(tokens_in), 0) + COALESCE(SUM(tokens_out), 0) "
                "AS tok FROM audit_log WHERE tenant_id = ? AND model IS NOT NULL "
                "GROUP BY model", (tenant_id,),
            )}
        return {"requests_llm": int(t["n"]), "tokens_in": int(t["tin"]),
                "tokens_out": int(t["tout"]),
                "by_model": {k: int(v) for k, v in par_modele.items()}}

    def user_history(self, tenant_id: str, user_id: str, limit: int = 30) -> list:
        """Historique d'UN utilisateur (ses propres questions et reponses)."""
        limit = max(1, min(int(limit), 200))
        with self._connexion() as cx:
            lignes = cx.execute(
                "SELECT ts, request_id, event_type, question, mode, departement, "
                "answer_excerpt, sources, confidence, latency_ms FROM audit_log "
                "WHERE tenant_id = ? AND user_id = ? "
                f"AND event_type IN ({_marques(REQUETES)}) "
                "ORDER BY id DESC LIMIT ?",
                (tenant_id, user_id, *REQUETES, limit),
            ).fetchall()

        historique = []
        for r in lignes:
            try:
                sources = json.loads(r["sources"]) if r["sources"] else []
            except ValueError:
                sources = []
            historique.append({
                "request_id": r["request_id"], "ts": r["ts"],
                "event_type": r["event_type"], "question": r["question"],
                "mode": r["mode"], "departement": r["departement"],
                "answer": r["answer_excerpt"], "sources": sources,
                "confidence": r["confidence"], "latency_ms": r["latency_ms"],
            })
        return historique
