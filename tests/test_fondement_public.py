from app.services.rag_service import to_public
from rag.postcheck import verifier_fondement

EXTRAIT = [{"content": "Le chiffre d'affaires 2023 de la societe Exemple SA s'eleve a 120 millions de dirhams."}]
PHRASE = "Le chiffre d'affaires 2023 de la societe Exemple SA s'eleve a %s millions de dirhams [Source 1]."


def _res(**extra):
    return {"answer": "x", "mode": "RAG", "confidence": 0.9, "cited_sources": [], **extra}


def test_to_public_expose_le_fondement():
    assert to_public(_res(fondement={"score": 0.5}))["fondement"] == 0.5


def test_to_public_sans_fondement_donne_none():
    assert to_public(_res())["fondement"] is None
    assert to_public(_res(fondement={"score": None}))["fondement"] is None


def test_fondement_complet_quand_les_nombres_sont_dans_la_source():
    assert verifier_fondement(PHRASE % "120", EXTRAIT)["score"] == 1.0


def test_fondement_nul_quand_un_nombre_est_absent_de_la_source():
    assert verifier_fondement(PHRASE % "130", EXTRAIT)["score"] == 0.0


def test_fondement_none_sans_affirmation():
    assert verifier_fondement("Voici :", EXTRAIT)["score"] is None
