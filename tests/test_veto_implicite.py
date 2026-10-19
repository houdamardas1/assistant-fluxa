from rag import rbac


def _faux_resultats(scores):
    return [
        {"score": s, "fichier_source": f"F{i}.pdf", "page": i, "entreprise": "X",
         "access_roles": ["finance", "direction"], "departement": "finance",
         "type_document": "entreprise"}
        for i, s in enumerate(scores, start=1)
    ]


def _veto(monkeypatch, scores, entreprises=None):
    monkeypatch.setattr(rbac, "search_without_rbac",
                        lambda *a, **k: _faux_resultats(scores))
    return rbac.check_rbac_restriction("q", None, None, [], "it", [],
                                       entreprises_nommees=entreprises)


def test_correspondances_faibles_sans_entreprise_pas_de_veto(monkeypatch):
    assert _veto(monkeypatch, [0.61, 0.58, 0.57]) is False


def test_entreprise_nommee_veto_maintenu(monkeypatch):
    assert _veto(monkeypatch, [0.61, 0.58], entreprises={"UNIMER"}) is True


def test_correspondances_fortes_sans_entreprise_veto(monkeypatch):
    assert _veto(monkeypatch, [0.75, 0.74]) is True


def test_document_interdit_nomme_veto_meme_score_faible(monkeypatch):
    monkeypatch.setattr(rbac, "search_without_rbac", lambda *a, **k: [
        {"score": 0.55, "fichier_source": "Code_Obligations_Contrats_DOC.pdf", "page": i,
         "entreprise": None, "access_roles": ["juridique"], "departement": "juridique",
         "type_document": "public_reglementaire"} for i in (1, 2)])
    assert rbac.check_rbac_restriction(
        "Que dit le Code des obligations et des contrats ?", None, None, [], "rh", []) is True
