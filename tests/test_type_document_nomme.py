from rag.documents_nommes import corriger_type_question

NOMME = [{"_document_nomme": True}]
AUTRE = [{"score": 0.5}]


def test_document_nomme_valide_donne_rag():
    assert corriger_type_question("GENERALE", NOMME, True) == "ENTREPRISE"


def test_document_nomme_non_valide_donne_absent():
    assert corriger_type_question("GENERALE", NOMME, False) == "ABSENTE"


def test_sans_document_nomme_rien_ne_change():
    assert corriger_type_question("GENERALE", AUTRE, True) == "GENERALE"


def test_types_deja_rag_ou_absent_inchanges():
    assert corriger_type_question("ENTREPRISE", NOMME, False) == "ENTREPRISE"
    assert corriger_type_question("ABSENTE", NOMME, True) == "ABSENTE"
