from app.services import uploads

TEXTE = "Le chiffre d'affaires de la societe Atlas est de 12 MDH en 2024.\n".encode("utf-8")


def _fichier():
    return uploads.charger("note.txt", TEXTE)


def test_un_refus_du_modele_devient_un_message_standard_sans_source(monkeypatch):
    monkeypatch.setattr(uploads, "generate_answer",
                        lambda q, r, role, *a, **k: "Aucun des extraits fournis ne mentionne le chiffre d'affaires de Wafa Assurance.")
    r = uploads.repondre(_fichier(), "chiffre d'affaires Atlas", "finance")
    assert r["trouve"] is False and r["sources"] == [] and r["fondement"] is None
    assert "Je ne trouve pas cette information" in r["answer"]


def test_une_vraie_reponse_avec_renvoi_est_conservee(monkeypatch):
    monkeypatch.setattr(uploads, "generate_answer",
                        lambda q, r, role, *a, **k: "Le chiffre d'affaires d'Atlas est de 12 MDH en 2024 [1].")
    r = uploads.repondre(_fichier(), "chiffre d'affaires Atlas", "finance")
    assert r["trouve"] is True and len(r["sources"]) == 1


def test_une_reponse_qui_evoque_une_absence_mais_cite_reste_valide(monkeypatch):
    monkeypatch.setattr(uploads, "generate_answer",
                        lambda q, r, role, *a, **k: "Le chiffre d'affaires est de 12 MDH [1], mais le document ne mentionne pas le resultat net.")
    r = uploads.repondre(_fichier(), "chiffre d'affaires Atlas", "finance")
    assert r["trouve"] is True
