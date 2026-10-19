from rag.rbac import check_rbac_restriction


def test_document_nomme_accessible_leve_le_veto():
    resultats = [{"_document_nomme": True, "score": 0.30, "type_document": "public_reglementaire"}]
    assert check_rbac_restriction("q", None, None, [], "juridique", resultats) is False
