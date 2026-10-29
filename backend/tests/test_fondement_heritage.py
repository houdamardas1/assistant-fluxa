from rag.postcheck import verifier_fondement

EXTRAITS = [{"content": "3 mois cadres, 15 jours ouvriers, employ\u00e9s un mois et demi, 90 jours tribunal"}]


def test_puces_imbriquees_heritent_de_la_citation_du_groupe():
    texte = (
        "Dur\u00e9e de la p\u00e9riode d'essai :\n\n"
        "- Contrats \u00e0 dur\u00e9e ind\u00e9termin\u00e9e :\n"
        "  - 3 mois pour les cadres et assimil\u00e9s ;\n"
        "  - 1 mois et demi pour les employ\u00e9s ;\n"
        "  - 15 jours pour les ouvriers [Source 1].\n"
    )
    r = verifier_fondement(texte, EXTRAITS)
    assert r["unites"] == 3
    assert r["non_citees"] == 0
    assert r["score"] == 1.0


def test_puces_de_premier_niveau_n_heritent_pas():
    texte = (
        "- Le pr\u00e9avis est d\u00fb lorsque le licenciement est sans faute grave.\n"
        "- Apr\u00e8s six mois, le salari\u00e9 a droit \u00e0 une indemnit\u00e9 de licenciement.\n"
        "- Le d\u00e9lai est de 90 jours pour saisir le tribunal comp\u00e9tent [Source 1].\n"
    )
    r = verifier_fondement(texte, EXTRAITS)
    assert r["non_citees"] == 2


def test_ligne_vide_coupe_l_heritage():
    texte = (
        "- Groupe :\n"
        "  - Premier \u00e9l\u00e9ment sans aucune citation du tout ici ;\n\n"
        "  - Deuxi\u00e8me \u00e9l\u00e9ment avec citation pr\u00e9sente ici [Source 1].\n"
    )
    r = verifier_fondement(texte, EXTRAITS)
    assert r["non_citees"] == 1
