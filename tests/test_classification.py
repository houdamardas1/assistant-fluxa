import json
import os

import pytest

from rag.classification import (
    CLASSIFICATION_DOCUMENTS, HABILITATIONS, NIVEAUX, habilitation_suffisante,
    niveau_du_chunk,
)
from rag.config import ROLES_DISPONIBLES
from rag.rbac import _roles_avant_classification, effective_allowed_roles, est_accessible

INDEX = "data/index/metadata.json"


def test_tous_les_roles_ont_une_habilitation_valide():
    assert set(ROLES_DISPONIBLES) == set(HABILITATIONS)
    assert all(h in NIVEAUX for h in HABILITATIONS.values())
    assert all(n in NIVEAUX for n in CLASSIFICATION_DOCUMENTS.values())


def test_profil_insuffisamment_habilite_est_ecarte_meme_si_autorise_par_departement():
    chunk = {"fichier_source": "Wafa_Assurance_RFA_2025.pdf", "access_roles": ["marketing", "finance", "direction"]}
    assert effective_allowed_roles(chunk) == {"finance", "direction"}
    assert not est_accessible(chunk, "marketing")
    assert est_accessible(chunk, "finance")


def test_niveau_restreint_reserve_a_la_direction():
    chunk = {"classification": "RESTRICTED", "access_roles": ["finance", "direction", "tous"]}
    assert effective_allowed_roles(chunk) == {"direction", "tous"}


def test_document_non_classe_est_interne_et_role_inconnu_na_que_le_public():
    assert niveau_du_chunk({"fichier_source": "nouveau.pdf"}) == "INTERNAL"
    assert niveau_du_chunk({"classification": "INVENTE"}) == "INTERNAL"
    assert habilitation_suffisante("inconnu", "PUBLIC")
    assert not habilitation_suffisante("inconnu", "INTERNAL")
    assert habilitation_suffisante("marketing", "INTERNAL")
    assert not habilitation_suffisante("marketing", "CONFIDENTIAL")


@pytest.mark.skipif(not os.path.exists(INDEX), reason="index reel absent (CI)")
def test_index_reel_invariant_et_aucune_regression():
    m = json.load(open(INDEX, encoding="utf-8"))
    m = m if isinstance(m, list) else list(m.values())
    assert len(m) > 1000
    for c in m:
        apres = effective_allowed_roles(c)
        avant = _roles_avant_classification(c)
        assert apres <= avant
        assert all(habilitation_suffisante(r, niveau_du_chunk(c)) for r in apres)
        # avec la politique actuelle, aucun acces existant n'est retire
        assert apres == avant, (c.get("fichier_source"), sorted(avant - apres))
    inconnus = {c.get("fichier_source") for c in m} - set(CLASSIFICATION_DOCUMENTS)
    assert not inconnus, "documents sans classification : %s" % sorted(inconnus)


from app.services.rag_service import to_public


def test_les_sources_publiques_portent_leur_niveau():
    r = {"answer": "x", "mode": "RAG", "cited_sources": [
        (1, {"fichier_source": "Wafa_Assurance_RFA_2025.pdf", "page": 3, "entreprise": "Wafa_Assurance", "type_document": "entreprise"}),
        (2, {"fichier_source": "Code_du_Travail_Loi_65-99.pdf", "page": 9, "type_document": "public_reglementaire"}),
    ]}
    niveaux = [s["classification"] for s in to_public(r)["sources"]]
    assert niveaux == ["CONFIDENTIAL", "PUBLIC"]
