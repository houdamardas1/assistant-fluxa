"""
Tests de l'API (necessite : pip install pytest httpx).
Lancer depuis backend/ :  python -m pytest tests/test_api.py -v

Aucun appel Groq, aucun index reel : le service RAG est remplace par un faux.
"""
import json
import os
import sys
from pathlib import Path

os.environ["SECRET_KEY"] = "k" * 40          # avant l'import de app.core.config
os.environ["ENVIRONMENT"] = "development"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.security.auth import RateLimiter, create_access_token  # noqa: E402
from rag.llm import QuotaError  # noqa: E402

SECRET = "k" * 40


class FakeRag:
    n_chunks = 3

    def __init__(self):
        self.calls = []
        self.mode = "RAG"
        self.raises = None

    def ask(self, question, role):
        self.calls.append((question, role))
        if self.raises:
            raise self.raises
        return {
            "answer": "Reponse de test [Source 1]", "mode": self.mode,
            "departement": "finance", "confidence": 0.9,
            "cited_sources": [(1, {
                "fichier_source": "Wafa_Assurance_RFA_2025.pdf", "page": 64,
                "entreprise": "Wafa_Assurance", "type_document": "entreprise",
                "is_synthetic": False, "content": "CONTENU INTERNE", "score": 0.5,
            })],
            "all_results": [{"content": "CONTENU INTERNE"}],
        }


def tok(role, tenant="t1", user="u1"):
    return {"Authorization": "Bearer " + create_access_token(user, tenant, role, SECRET, 5)}


@pytest.fixture
def client(tmp_path):
    fake = FakeRag()
    app = create_app(rag_factory=lambda: fake, audit_path=str(tmp_path / "audit.db"),
                     users_path=str(tmp_path / "users.db"))
    with TestClient(app) as c:
        c.fake, c.app_ = fake, app
        yield c


def evenements(client):
    return [r["event_type"] for r in client.app_.state.audit.recent(50)][::-1]


def test_health_sans_auth(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "healthy", "index_loaded": True}


def test_ask_sans_jeton(client):
    r = client.post("/ask", json={"question": "Quel est le CA ?"})
    assert r.status_code == 401 and client.fake.calls == []
    assert evenements(client) == ["AUTH_FAILED"]


def test_ask_jeton_invalide(client):
    r = client.post("/ask", json={"question": "Quel est le CA ?"},
                    headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401 and "invalide" in r.json()["detail"].lower()


def test_ask_ok_et_role_vient_du_jeton(client):
    r = client.post("/ask", json={"question": "Quel est le CA ?"}, headers=tok("finance"))
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "RAG" and d["sources"][0]["page"] == 64
    assert "CONTENU INTERNE" not in r.text          # aucun contenu de chunk expose
    assert client.fake.calls == [("Quel est le CA ?", "finance")]
    assert evenements(client) == ["ACCESS_GRANTED"]


def test_role_dans_le_corps_est_ignore(client):
    r = client.post("/ask", json={"question": "Quel est le CA ?", "role": "direction"},
                    headers=tok("rh"))
    assert r.status_code == 200 and client.fake.calls[0][1] == "rh"


def test_question_trop_courte(client):
    assert client.post("/ask", json={"question": "a"}, headers=tok("rh")).status_code == 422


def test_acces_refuse_journalise(client):
    client.fake.mode = "HORS_PERIMETRE"
    assert client.post("/ask", json={"question": "Quel est le CA ?"}, headers=tok("rh")).status_code == 200
    assert evenements(client) == ["ACCESS_DENIED"]


def test_quota_503(client):
    client.fake.raises = QuotaError("429")
    r = client.post("/ask", json={"question": "Quel est le CA ?"}, headers=tok("finance"))
    assert r.status_code == 503 and evenements(client) == ["QUOTA_ERROR"]


def test_erreur_interne_500_sans_fuite(client):
    client.fake.raises = RuntimeError("secret interne /etc/passwd")
    r = client.post("/ask", json={"question": "Quel est le CA ?"}, headers=tok("finance"))
    assert r.status_code == 500 and "passwd" not in r.text and "reference" in r.json()["detail"]
    assert evenements(client) == ["ERROR"]


def test_limitation_de_debit(client):
    client.app_.state.limiter = RateLimiter(2, 60.0)
    h = tok("finance")
    codes = [client.post("/ask", json={"question": "Quel est le CA ?"}, headers=h).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post("/ask", json={"question": "Quel est le CA ?"}, headers=h)
    assert int(r.headers["Retry-After"]) >= 1 and "RATE_LIMITED" in evenements(client)


def test_admin_reserve_a_la_direction_et_isole_par_tenant(client):
    client.post("/ask", json={"question": "Quel est le CA ?"}, headers=tok("finance", tenant="t1"))
    client.post("/ask", json={"question": "Quel est le CA ?"}, headers=tok("finance", tenant="t2", user="u9"))
    assert client.get("/admin/audit/summary", headers=tok("finance")).status_code == 403
    r = client.get("/admin/audit/summary", headers=tok("direction", tenant="t1", user="boss"))
    assert r.status_code == 200
    assert r.json()["tenant_id"] == "t1" and r.json()["counts"].get("ACCESS_GRANTED") == 1
    rec = client.get("/admin/audit/recent", headers=tok("direction", tenant="t1", user="boss")).json()
    assert all(x["tenant_id"] == "t1" for x in rec)


def test_documents_exigent_auth_et_rbac(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    brut = tmp_path / "data" / "raw" / "wafa"
    brut.mkdir(parents=True)
    (brut / "w_chunks.json").write_text(json.dumps(
        {"file_name": "w.pdf", "company": "Wafa Assurance", "sector": "Assurance",
         "total_pages": 1, "total_chunks": 1, "chunks": ["texte confidentiel"]}), encoding="utf-8")
    app = create_app(rag_factory=lambda: FakeRag(), audit_path=str(tmp_path / "a.db"),
                     users_path=str(tmp_path / "users.db"))
    with TestClient(app) as c:
        assert c.get("/documents/").status_code == 401
        assert c.get("/documents/Wafa Assurance/chunks").status_code == 401
        # finance : autorise par RBAC_POLICY
        assert c.get("/documents/Wafa Assurance/chunks", headers=tok("finance")).json() == ["texte confidentiel"]
        assert len(c.get("/documents/", headers=tok("finance")).json()) == 1
        # marketing : non autorise -> 404 (comme une entreprise inexistante)
        assert c.get("/documents/Wafa Assurance", headers=tok("marketing")).status_code == 404
        assert c.get("/documents/", headers=tok("marketing")).json() == []


def test_cors_origines_explicites(client):
    ok = client.options("/ask", headers={"Origin": "http://localhost:3000",
                                          "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    ko = client.options("/ask", headers={"Origin": "http://evil.example",
                                          "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in ko.headers
