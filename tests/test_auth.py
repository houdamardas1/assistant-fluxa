"""Tests des routes /auth/token et /auth/me."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class FakeRag:
    n_chunks = 42

    def ask(self, question, user_role, tenant_id):
        return {
            "answer": f"Reponse a '{question}' pour {user_role}@{tenant_id}",
            "mode": "RAG",
            "confidence": 0.9,
            "sources": [],
            "departement": None,
        }


@pytest.fixture
def client(tmp_path):
    fake = FakeRag()
    app = create_app(
        rag_factory=lambda: fake,
        audit_path=str(tmp_path / "audit.db"),
    )
    with TestClient(app) as c:
        yield c


def test_token_route_ok(client):
    r = client.post("/auth/token", json={
        "role": "finance", "tenant": "demo", "user": "alice",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["access_token"]
    assert data["role"] == "finance"


def test_token_route_role_invalide(client):
    r = client.post("/auth/token", json={
        "role": "hacker", "tenant": "demo", "user": "alice",
    })
    assert r.status_code == 400


def test_token_route_tenant_vide(client):
    r = client.post("/auth/token", json={
        "role": "finance", "tenant": "", "user": "alice",
    })
    assert r.status_code == 422


def test_me_sans_jeton(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_avec_jeton(client):
    r = client.post("/auth/token", json={
        "role": "finance", "tenant": "demo", "user": "alice",
    })
    token = r.json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["user"] == "alice"
    assert data["role"] == "finance"
    assert data["tenant"] == "demo"


def test_me_jeton_invalide(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer fake.token"})
    assert r.status_code == 401