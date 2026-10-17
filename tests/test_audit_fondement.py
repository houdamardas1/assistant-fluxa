import sqlite3
from app.services.audit import AuditLog


def test_fondement_enregistre(tmp_path):
    a = AuditLog(str(tmp_path / "a.db"))
    assert a.record("ACCESS_GRANTED", "r1", tenant_id="t", fondement=0.6)
    assert a.record("NO_ANSWER", "r2", tenant_id="t")
    lignes = {r["request_id"]: r for r in a.recent(10)}
    assert lignes["r1"]["fondement"] == 0.6
    assert lignes["r2"]["fondement"] is None


def test_migration_ancienne_base(tmp_path):
    p = str(tmp_path / "ancienne.db")
    cx = sqlite3.connect(p)
    cx.executescript("""
    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
        request_id TEXT NOT NULL, tenant_id TEXT, user_id TEXT, role TEXT,
        event_type TEXT NOT NULL, question TEXT, mode TEXT, departement TEXT,
        sources TEXT, confidence REAL, latency_ms INTEGER,
        answer_excerpt TEXT, detail TEXT, client_ip TEXT);
    INSERT INTO audit_log (ts, request_id, event_type) VALUES ('2026-01-01', 'vieux', 'LOGIN');
    """)
    cx.commit(); cx.close()
    a = AuditLog(p)
    assert a.record("ACCESS_GRANTED", "neuf", fondement=1.0)
    lignes = {r["request_id"]: r for r in a.recent(10)}
    assert lignes["vieux"]["fondement"] is None
    assert lignes["neuf"]["fondement"] == 1.0
