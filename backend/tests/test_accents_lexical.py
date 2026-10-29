from rag.retrieval import score_lexical

CONTENU_ACCENTUE = "La p\u00e9riode d'essai est de trois mois, renouvelable une fois."
CONTENU_SANS_ACCENT = "La periode d'essai est de trois mois, renouvelable une fois."


def test_score_lexical_requete_sans_accents_contenu_accentue():
    avec = score_lexical(["p\u00e9riode", "essai"], [], None, CONTENU_ACCENTUE)
    sans = score_lexical(["periode", "essai"], [], None, CONTENU_ACCENTUE)
    assert avec > 0
    assert sans == avec


def test_score_lexical_requete_accentuee_contenu_sans_accent():
    sans = score_lexical(["periode", "essai"], [], None, CONTENU_SANS_ACCENT)
    avec = score_lexical(["p\u00e9riode", "essai"], [], None, CONTENU_SANS_ACCENT)
    assert sans > 0
    assert avec == sans
