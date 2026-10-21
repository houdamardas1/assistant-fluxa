"""
Tests des routes ajoutees : connexion, profil, historique, corpus, supervision.
Necessite : pip install pytest httpx.   python -m pytest tests/test_api_extras.py -v
"""
import os
import sys
from pathlib import Path

os.environ["SECRET_KEY"] = "k" * 40
os.environ["ENVIRONMENT"] = "development"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

MDP = "Mot-De-Passe-Solide-1"


def chunk(f, page, ent, dept, typ="entreprise"):
    return {"fichier_source": f, "page": page, "entreprise": ent, "departement": dept,
            "type_document": typ, "content": "x", "is_synthetic": False}


class FakeRag:
    n_chunks = 4
    metadata = [
        {**chunk("Wafa.pdf", 1, "Wafa_Assurance", "finance"), "tenant_id": "t1"},
        {**chunk("Wafa.pdf", 64, "Wafa_Assurance", "finance"), "tenant_id": "t1"},
        chunk("Unimer.pdf", 19, "Unimer", "direction"),
        chunk("Travail.pdf", 90, None, "rh", "public_reglementaire"),
    ]

    def __init__(self):
        self.mode = "RAG"

    def ask(self, question, role):
        return {
            "answer": f"Reponse pour {role}", "mode": self.mode, "departement": "finance",
            "confidence": 0.9,
            "cited_sources": [(1, {"fichier_source": "Wafa.pdf", "page": 64,
                                   "entreprise": "Wafa_Assurance", "type_document": "entreprise",
                                   "is_synthetic": False})],
        }


@pytest.fixture
def client(tmp_path):
    app = create_app(rag_factory=lambda: FakeRag(), audit_path=str(tmp_path / "a.db"),
                     users_path=str(tmp_path / "u.db"))
    with TestClient(app) as c:
        c.app_ = app
        users = app.state.users
        users.create_user("alice", MDP, "finance", "t1", "Alice B.")
        users.create_user("boss", MDP, "direction", "t1", "La Direction")
        users.create_user("bob", MDP, "rh", "t1", "Bob")
        users.create_user("autre", MDP, "finance", "t2")
        yield c


def connexion(client, username, mdp=MDP):
    r = client.post("/auth/login", json={"username": username, "password": mdp})
    return r


def en_tete(client, username):
    return {"Authorization": "Bearer " + connexion(client, username).json()["access_token"]}


def evenements(client):
    return [r["event_type"] for r in client.app_.state.audit.recent(100)][::-1]


def test_login_ok_et_jeton_utilisable(client):
    r = connexion(client, "alice")
    assert r.status_code == 200
    d = r.json()
    assert d["token_type"] == "bearer" and d["expires_in"] > 0
    assert d["user"] == {"username": "alice", "display_name": "Alice B.", "role": "finance", "tenant_id": "t1"}
    assert "LOGIN" in evenements(client)
    h = {"Authorization": "Bearer " + d["access_token"]}
    assert client.get("/auth/me", headers=h).json()["display_name"] == "Alice B."
    assert client.post("/ask", json={"question": "Quel est le CA ?"}, headers=h).status_code == 200


def test_login_refuse_message_identique(client):
    a = connexion(client, "alice", "mauvais-mot-de-passe")
    b = connexion(client, "inconnu", MDP)
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json() == {"detail": "Identifiants invalides."}
    assert evenements(client).count("AUTH_FAILED") == 2


def test_login_compte_desactive(client):
    client.app_.state.users.set_active("alice", False)
    assert connexion(client, "alice").status_code == 401


def test_login_anti_force_brute(client):
    codes = [connexion(client, "alice", "mauvais-mot-de-passe").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # meme avec le bon mot de passe, la fenetre est bloquee
    r = connexion(client, "alice")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_me_exige_un_jeton(client):
    assert client.get("/auth/me").status_code == 401


def test_historique_personnel(client):
    ha, hb = en_tete(client, "alice"), en_tete(client, "bob")
    client.post("/ask", json={"question": "question d'alice"}, headers=ha)
    client.post("/ask", json={"question": "question de bob"}, headers=hb)
    h = client.get("/me/history", headers=ha).json()
    assert [x["question"] for x in h] == ["question d'alice"]
    assert h[0]["mode"] == "RAG" and h[0]["sources"][0]["page"] == 64
    assert client.get("/me/history").status_code == 401


def test_historique_isole_par_tenant(client):
    client.post("/ask", json={"question": "t1"}, headers=en_tete(client, "alice"))
    assert client.get("/me/history", headers=en_tete(client, "autre")).json() == []


def test_corpus_filtre_par_role(client):
    fin = client.get("/corpus/stats", headers=en_tete(client, "alice")).json()
    assert [f["file"] for f in fin["files"]] == ["Wafa.pdf"] and fin["total_chunks"] == 2
    rh = client.get("/corpus/stats", headers=en_tete(client, "bob")).json()
    assert [f["file"] for f in rh["files"]] == ["Travail.pdf"]
    assert client.get("/corpus/stats").status_code == 401


def test_supervision_etendue(client):
    boss = en_tete(client, "boss")
    client.post("/ask", json={"question": "une question"}, headers=en_tete(client, "alice"))
    s = client.get("/admin/audit/summary", headers=boss).json()
    assert {"counts", "latency", "by_role"} <= set(s) and s["by_role"].get("finance") == 1
    t = client.get("/admin/audit/timeseries?days=7", headers=boss).json()
    assert len(t["days"]) == 7 and sum(d["requests"] for d in t["days"]) == 1
    assert client.get("/admin/audit/timeseries", headers=en_tete(client, "alice")).status_code == 403
