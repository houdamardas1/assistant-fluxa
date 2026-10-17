from rag.generation import nettoyer_espaces_citations as n


def test_double_espace_et_espace_avant_point():
    assert n("la cause  [Source 5, Source 8] .") == "la cause [Source 5, Source 8]."


def test_citation_retiree():
    assert n("apres six mois d'anciennete  .") == "apres six mois d'anciennete."


def test_typographie_francaise_inchangee():
    t = "Le taux est de 6,3 % ; voir l'article 62, al. 2."
    assert n(t) == t


def test_indentation_conservee():
    assert n("- puce\n  suite de ligne") == "- puce\n  suite de ligne"
