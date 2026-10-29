from types import SimpleNamespace

from app.services.audit import AuditLog
from rag import llm


def _faux_client(prompt, completion):
    class _C:
        def create(self, **kw):
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))
    return SimpleNamespace(chat=SimpleNamespace(completions=_C()))


def test_comptage_somme_des_appels(monkeypatch):
    monkeypatch.setattr(llm, "groq_client", _faux_client(100, 20))
    with llm.mesurer_usage() as u:
        llm._chat([{"role": "user", "content": "x"}], 0.0, 10)
        llm._chat([{"role": "user", "content": "y"}], 0.0, 10)
    assert (u.tokens_in, u.tokens_out, u.appels) == (200, 40, 2)
    assert u.as_audit()["tokens_in"] == 200


def test_sans_appel_pas_de_champs():
    with llm.mesurer_usage() as u:
        pass
    assert u.as_audit() == {}


def test_hors_mesure_ne_plante_pas(monkeypatch):
    monkeypatch.setattr(llm, "groq_client", _faux_client(1, 1))
    llm._chat([], 0.0, 1)


def test_audit_enregistre_et_agrege_les_tokens(tmp_path):
    audit = AuditLog(str(tmp_path / "a.db"))
    assert audit.record("ACCESS_GRANTED", "r1", tenant_id="t", model="m", tokens_in=100, tokens_out=20)
    assert audit.record("ACCESS_GRANTED", "r2", tenant_id="t", model="m", tokens_in=50, tokens_out=10)
    assert audit.record("ACCESS_DENIED", "r3", tenant_id="t")
    assert audit.record("ACCESS_GRANTED", "r4", tenant_id="autre", model="m", tokens_in=999, tokens_out=1)
    u = audit.usage_stats("t")
    assert (u["requests_llm"], u["tokens_in"], u["tokens_out"]) == (2, 150, 30)
    assert u["by_model"] == {"m": 180}
