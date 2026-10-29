from rag.postcheck import verifier_fondement

EXTR = [{"content": "Le chiffre d'affaires 2023 s'etablit a 2 225 millions de dirhams."}]
BON = "Le chiffre d'affaires 2023 atteint 2 225 millions de dirhams [Source 1]."


def test_ligne_soutenue():
    r = verifier_fondement(BON, EXTR)
    assert r["score"] == 1.0 and r["unites"] == 1 and r["details"] == []


def test_ligne_non_citee():
    r = verifier_fondement(BON.replace(" [Source 1]", ""), EXTR)
    assert r["score"] == 0.0 and r["non_citees"] == 1
    assert r["details"][0]["problemes"] == ["non_citee"]


def test_nombre_absent_des_extraits_cites():
    r = verifier_fondement(BON.replace("2 225", "3 100"), EXTR)
    assert r["score"] == 0.0 and r["nombres_non_soutenus"] == 1
    assert r["details"][0]["nombres"] == ["3100"]


def test_entete_et_puces():
    r = verifier_fondement("Regles generales du licenciement :\n- " + BON, EXTR)
    assert r["unites"] == 1 and r["score"] == 1.0


def test_citation_hors_plage_equivaut_a_non_citee():
    r = verifier_fondement(BON.replace("Source 1", "Source 9"), EXTR)
    assert r["non_citees"] == 1 and r["score"] == 0.0


def test_controle_lexical_indicatif_hors_score():
    extraits = [{"content": "Le non-respect des prescriptions de securite constitue une faute grave pouvant entrainer le licenciement sans preavis."}]
    t = "Le licenciement pour faute grave (vol, abus de confiance, ivresse, trahison) peut etre immediat [Source 1]."
    r = verifier_fondement(t, extraits)
    assert r["score"] == 1.0
    assert r["a_verifier_lexical"] == 1
    assert "confiance" in r["details"][0]["termes"] and "ivresse" in r["details"][0]["termes"]


def test_nombre_trouve_dans_la_seconde_source_citee():
    extraits = [{"content": "Le salarie peut saisir le tribunal competent."},
                {"content": "Le delai est de 90 jours a compter de la reception."}]
    t = "Le salarie dispose de 90 jours pour saisir le tribunal competent [Source 1, Source 2]."
    assert verifier_fondement(t, extraits)["score"] == 1.0


def test_accents_normalises():
    extraits = [{"content": "Le non-respect des prescriptions de securite et d'hygiene constitue une faute grave."}]
    t = "Le non-respect des prescriptions de s\u00e9curit\u00e9 et d'hygi\u00e8ne constitue une faute grave [Source 1]."
    r = verifier_fondement(t, extraits)
    assert r["score"] == 1.0 and r["a_verifier_lexical"] == 0


def test_texte_vide():
    r = verifier_fondement("", [])
    assert r["score"] is None and r["unites"] == 0
