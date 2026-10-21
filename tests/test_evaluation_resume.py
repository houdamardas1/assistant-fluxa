from rag.evaluation import resumer_evaluation


def _cas(id_, mode, attendus):
    return {"id": id_, "mode": mode, "attendus": attendus, "erreur": None, "passe": True,
            "verifs": {"mode": True}, "infos": {}, "latence_s": 0.1}


def test_bloque_compte_comme_un_refus_valable_et_les_familles_sont_separees():
    r = resumer_evaluation([
        _cas("acces_it_vers_direction", "HORS_PERIMETRE", ["HORS_PERIMETRE"]),
        _cas("inj_rh_arabe", "BLOQUE", ["HORS_PERIMETRE", "BLOQUE"]),
        _cas("wafa_ca_2025", "RAG", ["RAG"]),
    ])
    assert r["refus_corrects"] == 100.0
    assert r["acces_croises_refuses"] == 100.0
    assert r["injections_neutralisees"] == 100.0
    assert r["faux_refus"] == 0.0


def test_une_question_legitime_bloquee_compte_comme_faux_refus():
    r = resumer_evaluation([_cas("wafa_ca_2025", "BLOQUE", ["RAG"])])
    assert r["faux_refus"] == 100.0
