from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import kpi as kpi_api
from app.security.deps import get_principal
from app.services.report import fmt_valeur, fmt_variation
from rag.config import ROLES_DISPONIBLES
from rag.kpi import charger_kpi

try:
    import pymupdf
except ImportError:  # anciennes versions de PyMuPDF
    import fitz as pymupdf


class FauxAudit:
    def __init__(self):
        self.evenements = []

    def record(self, event_type, request_id, **kw):
        self.evenements.append((event_type, kw))


class FauxLimiteur:
    def __init__(self, ok=True):
        self.ok = ok

    def allow(self, cle):
        return self.ok

    def retry_after(self, cle):
        return 7


def _client(role, limiteur=None):
    app = FastAPI()
    app.include_router(kpi_api.router)
    app.state.audit = FauxAudit()
    app.state.limiter = limiteur or FauxLimiteur()
    app.dependency_overrides[get_principal] = lambda: SimpleNamespace(
        role=role, tenant_id="t1", user_id="u1")
    return TestClient(app), app.state.audit


def _texte(pdf: bytes) -> str:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return "\n".join(p.get_text() for p in doc)


@pytest.mark.parametrize("role", sorted(ROLES_DISPONIBLES))
def test_rapport_limite_au_role_sur_les_vrais_kpi(role):
    kpi = charger_kpi()
    visibles = kpi_api.kpi_visibles(role, kpi)
    client, audit = _client(role)
    r = client.get("/kpi/report.pdf")
    if not visibles:
        assert r.status_code == 404
        assert audit.evenements == []
        return
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    texte = _texte(r.content)
    toutes = {k["entreprise"].replace("_", " ") for k in kpi}
    vues = {k["entreprise"] for k in visibles}
    for e in toutes - vues:
        assert e not in texte, "entreprise interdite dans le PDF : " + e
    for e in vues:
        assert e in texte
    assert [e[0] for e in audit.evenements] == ["REPORT_EXPORTED"]
    assert audit.evenements[0][1]["role"] == role
    assert "kpi=%d" % len(visibles) in audit.evenements[0][1]["detail"]


def test_rapport_limite_de_debit():
    client, audit = _client("tous", FauxLimiteur(ok=False))
    r = client.get("/kpi/report.pdf")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "7"
    assert audit.evenements == []


def test_formats():
    assert fmt_valeur(12738) == "12 738"
    assert fmt_valeur(77.3) == "77,3"
    assert fmt_valeur(100) == "100"
    assert fmt_variation(-3.2) == "-3,2 %"
    assert fmt_variation(5.0) == "+5,0 %"
    assert fmt_variation(0) == "0,0 %"
