import pytest

from rag import rbac
from rag.tenancy import TENANT_CORPUS, contexte_tenant, tenant_courant, visible_pour_tenant

ENTREPRISE = {"fichier_source": "CDG_Capital_RFA_2024.pdf", "type_document": "entreprise"}
LOI = {"fichier_source": "Code_du_Travail_Loi_65-99.pdf", "type_document": "public_reglementaire"}


def test_sans_contexte_on_retombe_sur_le_tenant_du_corpus():
    assert tenant_courant() == TENANT_CORPUS
    assert visible_pour_tenant(ENTREPRISE)


def test_un_autre_tenant_ne_voit_pas_les_documents_d_entreprise():
    with contexte_tenant("autre"):
        assert not visible_pour_tenant(ENTREPRISE)


def test_les_textes_reglementaires_sont_partages():
    with contexte_tenant("autre"):
        assert visible_pour_tenant(LOI)


def test_un_chunk_marque_pour_un_tenant_reste_chez_lui():
    chunk = dict(ENTREPRISE, tenant_id="client-a")
    assert visible_pour_tenant(chunk, "client-a")
    assert not visible_pour_tenant(chunk, "client-b")


def test_le_contexte_est_restaure_apres_la_requete():
    with contexte_tenant("autre"):
        pass
    assert tenant_courant() == TENANT_CORPUS


def test_est_accessible_exige_le_bon_tenant_meme_avec_le_bon_role(monkeypatch):
    monkeypatch.setattr(rbac, "effective_allowed_roles", lambda c: {"finance"})
    assert rbac.est_accessible(ENTREPRISE, "finance")
    with contexte_tenant("autre"):
        assert not rbac.est_accessible(ENTREPRISE, "finance")
        assert rbac.est_accessible(LOI, "finance")
