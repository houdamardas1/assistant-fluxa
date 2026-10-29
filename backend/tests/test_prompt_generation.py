from types import SimpleNamespace

import rag.generation as g


def test_prompt_contient_les_regles_de_fidelite(monkeypatch):
    vus = {}

    def faux_chat(messages, **kwargs):
        vus["system"] = messages[0]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content="ok [Source 1]"))])

    monkeypatch.setattr(g, "_chat", faux_chat)
    res = [
        {"entreprise": "X", "fichier_source": "a.pdf", "page": 1,
         "content": "texte", "type_document": "public_reglementaire"}
        for _ in range(2)
    ]
    out = g.generate_answer("question ?", res, "rh")
    assert "valides vont de 1 a 2" in vus["system"]
    assert "AUCUN exemple chiffre" in vus["system"]
    assert out
