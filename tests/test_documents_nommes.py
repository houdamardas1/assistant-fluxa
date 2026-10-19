from rag.documents_nommes import detect_documents_nommes

DOC = "Code_Obligations_Contrats_DOC.pdf"
TRAVAIL = "Code_du_Travail_Loi_65-99.pdf"
CONSO = "Loi_31-08_Protection_Consommateur.pdf"
FICHIERS = [DOC, TRAVAIL, CONSO]


def test_nom_exact_du_document():
    q = "Quelles sont les principales dispositions de Code Obligations Contrats DOC ?"
    assert detect_documents_nommes(q, FICHIERS) == {DOC}


def test_formulation_naturelle():
    q = "Que dit le Code des obligations et des contrats sur la formation du contrat ?"
    assert detect_documents_nommes(q, FICHIERS) == {DOC}


def test_code_des_obligations_seul_ne_vise_pas_le_doc():
    q = "Que dit le Code des obligations sur les clauses abusives ?"
    assert detect_documents_nommes(q, FICHIERS) == set()


def test_code_du_travail_vise_le_travail_pas_le_doc():
    q = "Quelle est la dur\u00e9e de la p\u00e9riode d'essai selon le Code du Travail ?"
    assert detect_documents_nommes(q, FICHIERS) == {TRAVAIL}


def test_aucun_document_nomme():
    assert detect_documents_nommes("Qu'est-ce que l'inflation ?", FICHIERS) == set()


def test_titre_a_un_seul_mot_distinctif_ignore():
    assert detect_documents_nommes("Que dit la charte ?", ["Charte.pdf"]) == set()
