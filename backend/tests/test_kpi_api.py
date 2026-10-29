from app.api.kpi import kpi_visibles
from rag.kpi import charger_kpi


def _k(id, ent, annee, val, perim, roles):
    return {"id": id, "entreprise": ent, "indicateur": "chiffre_affaires",
            "libelle": "Chiffre d'affaires", "annee": annee, "valeur": val,
            "unite": "MDH", "perimetre": perim, "document": "X.pdf", "page": 1,
            "roles_autorises": roles, "statut": "verifie_extrait", "note": "n"}


KPI = [
    _k("a24", "Auto_Nejma", 2024, 110.0, "social", ["direction", "marketing"]),
    _k("a23", "Auto_Nejma", 2023, 100.0, "social", ["direction", "marketing"]),
    _k("u24", "Unimer", 2024, 90.0, "social", ["direction"]),
    _k("u23", "Unimer", 2023, 100.0, "consolide", ["direction"]),
    _k("c24", "CDG_Capital", 2024, 10.0, "non_precise", ["direction", "finance"]),
    _k("c23", "CDG_Capital", 2023, 5.0, "non_precise", ["direction", "finance"]),
]


def _ids(role):
    return {x["id"] for x in kpi_visibles(role, KPI)}


def test_filtrage_par_role():
    assert _ids("rh") == set()
    assert _ids("marketing") == {"a24", "a23"}
    assert _ids("finance") == {"c24", "c23"}
    assert _ids("direction") == {"a24", "a23", "u24", "u23", "c24", "c23"}


def test_variation_meme_perimetre():
    par_id = {x["id"]: x for x in kpi_visibles("direction", KPI)}
    assert par_id["a24"]["variation_pct"] == 10.0
    assert par_id["a24"]["annee_precedente"] == 2023
    assert par_id["a23"]["variation_pct"] is None


def test_pas_de_variation_si_perimetre_different_ou_non_precise():
    par_id = {x["id"]: x for x in kpi_visibles("direction", KPI)}
    assert par_id["u24"]["variation_pct"] is None
    assert par_id["c24"]["variation_pct"] is None


def test_affichage_et_tri():
    sortie = kpi_visibles("direction", KPI)
    assert sortie[0]["entreprise"] == "Auto Nejma" and sortie[0]["annee"] == 2024
    assert all(x["verifie"] is True for x in sortie)


def test_table_reelle():
    reel = charger_kpi()
    assert len(kpi_visibles("direction", reel)) == len(reel) == 12
    assert kpi_visibles("rh", reel) == []
