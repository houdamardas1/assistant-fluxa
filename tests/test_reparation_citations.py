from rag.generation import reparer_citations, retirer_citations_invalides

EXTRAITS = [
    {"content": "Article 5 : texte sans rapport"},
    {"content": "Article 35 : le salarie peut etre licencie pour faute grave"},
    {"content": "Art. 52 : delai de preavis"},
    {"content": "Article 520 : autre disposition"},
]


def test_remplace_un_numero_darticle_par_la_source():
    assert reparer_citations("Faute grave [Source 35].", EXTRAITS) == "Faute grave [Source 2]."


def test_bloc_mixte_valide_plus_article():
    r = reparer_citations("Regle [Source 1, Source 35].", EXTRAITS)
    assert r == "Regle [Source 1, Source 2]."


def test_article_52_ne_correspond_pas_a_520():
    assert reparer_citations("Preavis [Source 52].", EXTRAITS) == "Preavis [Source 3]."


def test_article_ambigu_ou_absent_laisse_inchange():
    deux = EXTRAITS + [{"content": "Article 35 : repete dans un autre extrait"}]
    assert reparer_citations("X [Source 35].", deux) == "X [Source 35]."
    assert reparer_citations("X [Source 99].", EXTRAITS) == "X [Source 99]."


def test_blocs_valides_ou_sans_mot_source_intacts():
    assert reparer_citations("X [Source 2] et [35]", EXTRAITS) == "X [Source 2] et [35]"


def test_enchainement_avec_retrait_des_numeros_non_resolus():
    texte = reparer_citations("A [Source 35]. B [Source 99].", EXTRAITS)
    assert retirer_citations_invalides(texte, len(EXTRAITS)) == "A [Source 2]. B."
