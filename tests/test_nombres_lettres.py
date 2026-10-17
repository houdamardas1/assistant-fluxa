from rag.postcheck import _nombres_en_lettres as n, verifier_fondement


def test_conversion():
    assert n("cinquante-deux semaines") == {"52"}
    assert n("quatre-vingt-dix jours") == {"90"}
    assert n("soixante et onze") == {"71"}
    assert n("dix-huit ans") == {"18"}
    assert n("deux cents") == {"200"}
    assert n("mille deux cent trente") == {"1230"}
    assert n("une indemnite de six mois") == set()


def test_52_semaines_en_lettres_dans_l_extrait():
    extraits = [{"content": "Article 55 L'indemnite est calculee sur la moyenne des salaires percus au cours des cinquante-deux semaines qui ont precede la rupture."}]
    t = "Le montant est calcule sur la moyenne des salaires des 52 semaines precedant la rupture [Source 1]."
    r = verifier_fondement(t, extraits)
    assert r["score"] == 1.0 and r["nombres_non_soutenus"] == 0


def test_nombre_vraiment_absent_reste_signale():
    extraits = [{"content": "cinquante-deux semaines"}]
    t = "Le montant est calcule sur la moyenne des 53 semaines precedant la rupture [Source 1]."
    assert verifier_fondement(t, extraits)["nombres_non_soutenus"] == 1
