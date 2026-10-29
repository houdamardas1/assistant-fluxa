import json
from pathlib import Path

CHEMIN = Path(__file__).resolve().parents[1] / "data" / "kpi" / "kpi_v1.json"
CHAMPS = {"id", "entreprise", "indicateur", "libelle", "annee", "valeur", "unite",
          "perimetre", "document", "page", "roles_autorises", "statut"}
PERIMETRES = {"social", "consolide", "non_precise"}
ROLES = {"tous", "finance", "direction", "it", "rh", "commerce", "juridique", "marketing"}
# Politique d'acces reelle par entreprise (cf. audit RBAC au demarrage)
POLITIQUE = {
    "Wafa_Assurance": {"direction", "finance", "tous"},
    "CDG_Capital": {"direction", "finance", "tous"},
    "Unimer": {"direction", "tous"},
    "Auto_Nejma": {"direction", "marketing", "tous"},
}


def _kpi():
    return json.loads(CHEMIN.read_text(encoding="utf-8"))["kpi"]


def test_identifiants_uniques():
    ids = [k["id"] for k in _kpi()]
    assert len(ids) == len(set(ids))


def test_champs_et_types():
    for k in _kpi():
        assert CHAMPS <= set(k), k["id"]
        assert isinstance(k["valeur"], (int, float)) and k["valeur"] > 0, k["id"]
        assert k["unite"] == "MDH", k["id"]
        assert isinstance(k["page"], int) and k["page"] >= 1, k["id"]
        assert isinstance(k["annee"], int) and 2000 <= k["annee"] <= 2030, k["id"]
        assert k["perimetre"] in PERIMETRES, k["id"]
        assert k["document"].lower().endswith(".pdf"), k["id"]


def test_roles_coherents_avec_la_politique_acces():
    for k in _kpi():
        roles = set(k["roles_autorises"])
        assert roles <= ROLES, k["id"]
        assert roles == POLITIQUE[k["entreprise"]], k["id"]
