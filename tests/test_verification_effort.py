from types import SimpleNamespace

from rag import verification as V

CONTEXTES = [{"content": "La periode d'essai est de trois mois.", "fichier_source": "x.pdf",
              "page": 1, "entreprise": None, "score": 0.9, "type_document": "public_reglementaire"}]
JSON_OK = '{"can_answer": true, "confidence": 0.9, "extraits": [1]}'


def _reponse():
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=JSON_OK))], usage=None)


def _faux_client(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_la_verification_demande_un_effort_de_raisonnement_faible(monkeypatch):
    appels = []
    monkeypatch.setattr(V, "_compter", lambda r: r)
    monkeypatch.setattr(V, "groq_client", _faux_client(lambda **k: appels.append(k) or _reponse()))
    can_answer, confidence, erreur, extraits = V.verify_relevance("periode d'essai", CONTEXTES)
    assert appels[0].get("reasoning_effort") == "low"
    assert can_answer is True and erreur is False and extraits == [1]


def test_repli_sans_effort_si_le_modele_refuse_le_parametre(monkeypatch):
    appels = []

    def create(**k):
        appels.append(k)
        if "reasoning_effort" in k:
            raise ValueError("reasoning_effort non supporte par ce modele")
        return _reponse()

    monkeypatch.setattr(V, "_compter", lambda r: r)
    monkeypatch.setattr(V, "groq_client", _faux_client(create))
    can_answer, _, erreur, _ = V.verify_relevance("periode d'essai", CONTEXTES)
    assert len(appels) == 2 and "reasoning_effort" not in appels[1]
    assert can_answer is True and erreur is False
