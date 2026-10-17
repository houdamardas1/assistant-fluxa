import json
from pathlib import Path

import pytest

from rag.kpi import charger_kpi, trouver_passage

RACINE = Path(__file__).resolve().parent.parent
META = RACINE / "data" / "index" / "metadata.json"
PERIMETRES = {"social", "consolide", "non_precise"}


def test_table_coherente():
    kpi = charger_kpi()
    assert len(kpi) == 12
    ids = [k["id"] for k in kpi]
    assert len(ids) == len(set(ids))
    for k in kpi:
        assert k["perimetre"] in PERIMETRES
        assert k["statut"] == "verifie_extrait"
        assert k["roles_autorises"]
    cles = [(k["entreprise"], k["indicateur"], k["annee"], k["perimetre"]) for k in kpi]
    assert len(cles) == len(set(cles)), "deux KPI identiques (entreprise, indicateur, annee, perimetre)"


def test_auto_nejma_valeurs():
    par_id = {k["id"]: k for k in charger_kpi()}
    assert par_id["auto_nejma_ca_social_2023"]["valeur"] == 2225
    assert par_id["auto_nejma_ca_conso_2023"]["valeur"] == 2275
    assert par_id["auto_nejma_resultat_net_social_2023"]["valeur"] == 160.3
    assert all(par_id[i]["entreprise"] == "Auto_Nejma" for i in par_id if i.startswith("auto_nejma_"))


@pytest.mark.skipif(not META.exists(), reason="index absent (hors machine locale)")
def test_chaque_valeur_est_dans_sa_page():
    meta = json.loads(META.read_text(encoding="utf-8"))
    manquants = [k["id"] for k in charger_kpi() if trouver_passage(meta, k) is None]
    assert manquants == [], "valeur introuvable dans la page citee : %s" % manquants
