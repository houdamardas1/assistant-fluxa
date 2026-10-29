from rag import kpi as K

NOMS = {"Wafa_Assurance", "Unimer"}


def _k(id, ent, ind, annee, val, perim, doc, page, roles):
    return {"id": id, "entreprise": ent, "indicateur": ind, "annee": annee,
            "valeur": val, "unite": "MDH", "perimetre": perim, "document": doc,
            "page": page, "roles_autorises": roles}


WAFA = _k("wafa_ca", "Wafa_Assurance", "chiffre_affaires", 2025, 12738, "social",
          "Wafa.pdf", 64, ["direction", "finance", "tous"])
UNIMER = _k("unimer_ca", "Unimer", "chiffre_affaires", 2024, 806.449, "social",
            "Unimer.pdf", 16, ["direction", "tous"])
# KPI FICTIF, uniquement pour tester l'ambiguite de perimetre
WAFA_CONSO = _k("wafa_ca_conso", "Wafa_Assurance", "chiffre_affaires", 2025, 20000,
                "consolide", "Wafa.pdf", 70, ["direction", "finance", "tous"])
KPI = [WAFA, UNIMER]

Q_WAFA = "Quel est le chiffre d'affaires de Wafa Assurance en 2025 ?"

META = [
    {"entreprise": "Wafa_Assurance", "fichier_source": "Wafa.pdf", "page": 64,
     "content": "Le chiffre d'affaires de l'exercice 2025 ressort a 12 738 MDH"},
    {"entreprise": "Unimer", "fichier_source": "Unimer.pdf", "page": 16,
     "content": "Unimer SA affiche un chiffre d'affaires de 806.449 KMAD"},
]


def test_formater_valeur():
    assert K.formater_valeur(12738) == "12 738"
    assert K.formater_valeur(77.3) == "77,3"
    assert K.formater_valeur(806.449) == "806,449"
    assert K.formater_valeur(619) == "619"


def test_reponse_unique_autorisee():
    assert K.chercher_kpi(Q_WAFA, "direction", NOMS, KPI)["id"] == "wafa_ca"
    assert K.chercher_kpi(Q_WAFA, "finance", NOMS, KPI)["id"] == "wafa_ca"


def test_role_non_autorise():
    assert K.chercher_kpi(Q_WAFA, "rh", NOMS, KPI) is None
    q = "Quel est le chiffre d'affaires d'Unimer en 2024 ?"
    assert K.chercher_kpi(q, "direction", NOMS, KPI)["id"] == "unimer_ca"
    assert K.chercher_kpi(q, "finance", NOMS, KPI) is None


def test_annee_absente_de_la_table():
    q = "Quel est le chiffre d'affaires de Wafa Assurance en 2024 ?"
    assert K.chercher_kpi(q, "direction", NOMS, KPI) is None


def test_sans_annee_ou_deux_annees():
    assert K.chercher_kpi("Quel est le chiffre d'affaires de Wafa Assurance ?",
                          "direction", NOMS, KPI) is None
    q = "Quel est le chiffre d'affaires de Wafa Assurance en 2024 et en 2025 ?"
    assert K.chercher_kpi(q, "direction", NOMS, KPI) is None


def test_deux_entreprises():
    q = "Quel est le chiffre d'affaires de Wafa Assurance et d'Unimer en 2024 ?"
    assert K.chercher_kpi(q, "direction", NOMS, KPI) is None


def test_ambiguite_de_perimetre():
    deux = [WAFA, WAFA_CONSO]
    assert K.chercher_kpi(Q_WAFA, "direction", NOMS, deux) is None
    q = "Quel est le chiffre d'affaires consolid\u00e9 de Wafa Assurance en 2025 ?"
    assert K.chercher_kpi(q, "direction", NOMS, deux)["id"] == "wafa_ca_conso"


def test_passage_present_et_absent():
    assert K.trouver_passage(META, WAFA)["page"] == 64
    sans_valeur = [dict(META[0], content="texte sans le chiffre")]
    assert K.trouver_passage(sans_valeur, WAFA) is None


def test_repondre_depuis_kpi(monkeypatch):
    monkeypatch.setattr(K, "charger_kpi", lambda: KPI)
    rep = K.repondre_depuis_kpi(Q_WAFA, "direction", META)
    assert "12 738 MDH" in rep["answer"] and "[Source 1]" in rep["answer"]
    assert rep["passage"]["page"] == 64
    assert K.repondre_depuis_kpi(Q_WAFA, "rh", META) is None
    sans_valeur = [dict(META[0], content="texte sans le chiffre")]
    assert K.repondre_depuis_kpi(Q_WAFA, "direction", sans_valeur) is None
