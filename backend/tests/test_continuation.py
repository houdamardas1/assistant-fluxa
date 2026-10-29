from rag.continuation import completer_extraits, est_coupe


def _c(texte, page, doc="a.pdf"):
    return {"content": texte, "page": page, "fichier_source": doc}


SUITE = "ann\u00e9e ou fraction d'ann\u00e9e de travail sans toutefois d\u00e9passer le plafond de 36 mois. Article 42 Lorsqu'un salari\u00e9 rompt"


def test_complete_au_saut_de_page():
    ch = [_c("le salaire d'un mois et demi par - 28 -", 28), _c(SUITE, 29)]
    assert completer_extraits(ch) == [0]
    assert ch[0]["content"].endswith("plafond de 36 mois.")
    assert "- 28 -" not in ch[0]["content"]
    assert "Article 42" not in ch[0]["content"]


def test_idempotent():
    ch = [_c("un mois et demi par - 28 -", 28), _c(SUITE, 29)]
    completer_extraits(ch)
    assert completer_extraits(ch) == []


def test_phrase_finie_inchangee():
    ch = [_c("La phrase est finie. - 28 -", 28), _c(SUITE, 29)]
    assert completer_extraits(ch) == []
    assert ch[0]["content"] == "La phrase est finie. - 28 -"


def test_suite_en_majuscule_non_ajoutee():
    ch = [_c("fin de page sans point", 28), _c("Article 42 Lorsqu'un salari\u00e9", 29)]
    assert completer_extraits(ch) == []


def test_meme_page_ou_autre_document_ignores():
    assert completer_extraits([_c("coupe par", 28), _c(SUITE, 28)]) == []
    assert completer_extraits([_c("coupe par", 28, "a.pdf"), _c(SUITE, 29, "b.pdf")]) == []


def test_est_coupe():
    assert est_coupe("un mois et demi par - 28 -")
    assert not est_coupe("fin de phrase. - 28 -")
from rag.continuation import completer_extraits


def test_rapport_en_colonnes_non_complete():
    ch = [{"content": "texte coupe par", "page": 5, "fichier_source": "r.pdf", "type_document": "rapport_annuel"},
          {"content": "suite d'une autre colonne.", "page": 6, "fichier_source": "r.pdf", "type_document": "rapport_annuel"}]
    assert completer_extraits(ch, {"public_reglementaire"}) == []
    assert ch[0]["content"] == "texte coupe par"


def test_texte_juridique_complete():
    ch = [{"content": "texte coupe par - 5 -", "page": 5, "fichier_source": "c.pdf", "type_document": "public_reglementaire"},
          {"content": "ann\u00e9e de travail. Article 2 suite", "page": 6, "fichier_source": "c.pdf", "type_document": "public_reglementaire"}]
    assert completer_extraits(ch, {"public_reglementaire"}) == [0]
from rag.continuation import completer_extraits


def test_rapport_en_colonnes_non_complete():
    ch = [{"content": "texte coupe par", "page": 5, "fichier_source": "r.pdf", "type_document": "rapport_annuel"},
          {"content": "suite d'une autre colonne.", "page": 6, "fichier_source": "r.pdf", "type_document": "rapport_annuel"}]
    assert completer_extraits(ch, {"public_reglementaire"}) == []
    assert ch[0]["content"] == "texte coupe par"


def test_texte_juridique_complete():
    ch = [{"content": "texte coupe par - 5 -", "page": 5, "fichier_source": "c.pdf", "type_document": "public_reglementaire"},
          {"content": "ann\u00e9e de travail. Article 2 suite", "page": 6, "fichier_source": "c.pdf", "type_document": "public_reglementaire"}]
    assert completer_extraits(ch, {"public_reglementaire"}) == [0]
