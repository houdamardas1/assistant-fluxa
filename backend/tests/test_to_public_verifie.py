from app.services.rag_service import to_public

PASSAGE = {"fichier_source": "a.pdf", "page": 3, "entreprise": "X",
           "type_document": "entreprise", "is_synthetic": False}


def _res(**extra):
    base = {"answer": "ok", "mode": "RAG", "departement": None, "confidence": 1.0,
            "cited_sources": [(1, PASSAGE)]}
    base.update(extra)
    return base


def test_source_verifiee_pour_une_reponse_kpi():
    pub = to_public(_res(source_donnees="kpi_verifie"))
    assert pub["sources"][0]["verifie"] is True


def test_source_non_verifiee_par_defaut():
    assert to_public(_res())["sources"][0]["verifie"] is False
