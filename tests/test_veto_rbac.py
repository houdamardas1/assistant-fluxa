from rag import rbac


def _chunk(dept, roles, score, fichier, page=1, type_doc="public_reglementaire"):
    return {"fichier_source": fichier, "page": page, "departement": dept,
            "access_roles": roles, "type_document": type_doc, "score": score}


def _preparer(monkeypatch):
    interdits = [_chunk("juridique", ["juridique"], 0.67, "Obligations.pdf", 139),
                 _chunk("juridique", ["juridique"], 0.67, "Obligations.pdf", 13),
                 _chunk("direction", ["direction"], 0.66, "Unimer.pdf", 25, "entreprise")]
    monkeypatch.setattr(rbac, "search_without_rbac", lambda *a, **k: interdits)
    monkeypatch.setattr(rbac, "effective_allowed_roles", lambda r: set(r.get("access_roles", [])))
    monkeypatch.setattr(rbac, "est_accessible", lambda c, role: role in c.get("access_roles", []))


def _autorises(score=0.53):
    return [_chunk("rh", ["rh"], score, "Travail.pdf", 43)]


def _appel(autorises, **kw):
    return rbac.check_rbac_restriction("q", None, None, list(autorises), "rh", autorises, **kw)


def test_comportement_historique_conserve(monkeypatch):
    _preparer(monkeypatch)
    assert _appel(_autorises()) is True


def test_departement_autorise_couvert_pas_de_veto(monkeypatch):
    _preparer(monkeypatch)
    assert _appel(_autorises(), departement_autorise="rh", entreprises_nommees=set()) is False


def test_entreprise_nommee_garde_le_veto(monkeypatch):
    _preparer(monkeypatch)
    assert _appel(_autorises(), departement_autorise="rh", entreprises_nommees={"Unimer"}) is True


def test_couverture_trop_faible_garde_le_veto(monkeypatch):
    _preparer(monkeypatch)
    assert _appel(_autorises(0.40), departement_autorise="rh", entreprises_nommees=set()) is True
