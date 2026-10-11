"""Tests de la logique pure (sans FastAPI) : python tests/test_api_core.py"""
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import jwt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.security.auth import (  # noqa: E402
    AuthError, RateLimiter, check_secret, create_access_token, decode_token,
)
from app.services.audit import AuditLog  # noqa: E402
from app.services.rag_service import RagService, event_for_mode, to_public  # noqa: E402

SECRET = "x" * 40
ROLES = ["tous", "finance", "direction", "it", "rh", "commerce", "juridique", "marketing"]
n_ok = 0


def ok(nom, cond):
    global n_ok
    assert cond, f"ECHEC : {nom}"
    n_ok += 1


def leve(nom, fn, exc=AuthError):
    global n_ok
    try:
        fn()
    except exc:
        n_ok += 1
        return
    raise AssertionError(f"ECHEC (aucune exception) : {nom}")


# ---- JWT -------------------------------------------------------------------
t = create_access_token("alice", "demo", "finance", SECRET, 5)
p = decode_token(t, SECRET, ROLES)
ok("aller-retour", (p.user_id, p.tenant_id, p.role) == ("alice", "demo", "finance"))
leve("jeton expire", lambda: decode_token(
    create_access_token("a", "t", "finance", SECRET, 1, now=time.time() - 3600), SECRET, ROLES))
leve("mauvais secret", lambda: decode_token(t, "y" * 40, ROLES))
leve("jeton altere", lambda: decode_token(t[:-3] + ("AAA" if t[-3:] != "AAA" else "BBB"), SECRET, ROLES))
leve("chaine quelconque", lambda: decode_token("n'importe quoi", SECRET, ROLES))
leve("alg none", lambda: decode_token(
    jwt.encode({"sub": "a", "tenant_id": "t", "role": "direction", "exp": int(time.time()) + 600},
               None, algorithm="none"), SECRET, ROLES))
leve("role inconnu", lambda: decode_token(
    create_access_token("a", "t", "superadmin", SECRET), SECRET, ROLES))
leve("tenant manquant", lambda: decode_token(
    jwt.encode({"sub": "a", "role": "finance", "exp": int(time.time()) + 600}, SECRET, algorithm="HS256"),
    SECRET, ROLES))
leve("exp manquant", lambda: decode_token(
    jwt.encode({"sub": "a", "tenant_id": "t", "role": "finance"}, SECRET, algorithm="HS256"), SECRET, ROLES))
leve("sub manquant", lambda: decode_token(
    jwt.encode({"tenant_id": "t", "role": "finance", "exp": int(time.time()) + 600}, SECRET, algorithm="HS256"),
    SECRET, ROLES))
leve("signature HS512 refusee", lambda: decode_token(
    jwt.encode({"sub": "a", "tenant_id": "t", "role": "finance", "exp": int(time.time()) + 600},
               SECRET, algorithm="HS512"), SECRET, ROLES))

# ---- check_secret ----------------------------------------------------------
ok("secret fort", check_secret("z" * 40, "production") is None)
ok("secret par defaut en dev : avertissement",
   "valeur par defaut" in check_secret("your-secret-key-here-change-in-production", "development"))
leve("secret par defaut en prod : refus",
     lambda: check_secret("your-secret-key-here-change-in-production", "production"), RuntimeError)
leve("secret court en staging : refus", lambda: check_secret("abc", "staging"), RuntimeError)

# ---- RateLimiter -----------------------------------------------------------
h = [0.0]
rl = RateLimiter(3, 60.0, clock=lambda: h[0])
ok("3 appels autorises", all(rl.allow("u") for _ in range(3)))
ok("4e refuse", not rl.allow("u"))
ok("autre cle independante", rl.allow("v"))
ok("retry_after > 0", rl.retry_after("u") > 0)
h[0] = 61.0
ok("fenetre glissante : reautorise", rl.allow("u"))

# ---- Audit -----------------------------------------------------------------
tmp = tempfile.mkdtemp()
audit = AuditLog(os.path.join(tmp, "sub", "audit.db"))
ok("record 1", audit.record("ACCESS_GRANTED", "r1", tenant_id="A", user_id="u1", role="finance",
                            question="q" * 5000, mode="RAG", sources=[{"n": 1}], latency_ms=12,
                            answer="a" * 5000, client_ip="1.2.3.4"))
audit.record("ACCESS_DENIED", "r2", tenant_id="A", user_id="u2", role="rh", question="x", mode="HORS_PERIMETRE")
audit.record("ACCESS_GRANTED", "r3", tenant_id="B", user_id="u3", role="finance", question="y", mode="RAG")
audit.record("AUTH_FAILED", "r4", detail="jeton invalide")
ok("compteurs globaux", audit.counts() == {"ACCESS_DENIED": 1, "ACCESS_GRANTED": 2, "AUTH_FAILED": 1})
ok("isolation par tenant", audit.counts(tenant_id="A") == {"ACCESS_DENIED": 1, "ACCESS_GRANTED": 1})
rec = audit.recent(10, tenant_id="A")
ok("recent filtre par tenant", {r["request_id"] for r in rec} == {"r1", "r2"})
ok("question tronquee", len([r for r in rec if r["request_id"] == "r1"][0]["question"]) == 2000)
ok("limite recent bornee", len(audit.recent(100000)) == 4)
# Injection SQL dans les champs : stocke comme texte, table intacte
audit.record("ACCESS_GRANTED", "r5", tenant_id="A", question="'); DROP TABLE audit_log; --")
ok("injection SQL inoperante", audit.counts(tenant_id="A")["ACCESS_GRANTED"] == 2)
bad = AuditLog(tmp)  # un dossier n'est pas une base : ne doit pas lever
ok("panne d'audit : record() ne leve pas", bad.record("ERROR", "rx") is False)

# ---- Service RAG -----------------------------------------------------------
appels = []


def faux_pipeline(q, model, index, metadata, role):
    appels.append((q, role))
    return {
        "answer": "reponse", "mode": "RAG", "departement": "finance", "confidence": 0.987,
        "cited_sources": [(1, {"fichier_source": "W.pdf", "page": 64, "entreprise": "Wafa_Assurance",
                               "type_document": "entreprise", "is_synthetic": False,
                               "content": "SECRET INTERNE", "score": 0.9})],
        "all_results": [{"content": "SECRET"}],
    }


svc = RagService(index=object(), metadata=[1, 2, 3], model=object(), pipeline=faux_pipeline)
res = svc.ask("question", "finance")
ok("role transmis au pipeline", appels == [("question", "finance")])
pub = to_public(res)
ok("vue publique sans contenu ni score", "SECRET" not in str(pub) and "score" not in str(pub))
ok("source exposee", pub["sources"][0]["fichier"] == "W.pdf" and pub["sources"][0]["page"] == 64)
ok("confiance arrondie", pub["confidence"] == 0.99)
ok("n_chunks", svc.n_chunks == 3)
ok("evenements", [event_for_mode(m) for m in ("RAG", "HORS_PERIMETRE", "ABSENT", "CLARIFICATION", "GENERAL")]
   == ["ACCESS_GRANTED", "ACCESS_DENIED", "NO_ANSWER", "CLARIFICATION_REQUESTED", "ACCESS_GRANTED"])

print(f"{n_ok} verifications reussies")
