from rag import verification


class _Completions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return "ok"


class _Client:
    def __init__(self):
        self.completions = _Completions()
        self.chat = self


def test_effort_de_verification_par_defaut_medium(monkeypatch):
    monkeypatch.delenv("GROQ_VERIFY_EFFORT", raising=False)
    client = _Client()
    monkeypatch.setattr(verification, "groq_client", client)
    verification._appel_verification(model="m", messages=[])
    assert client.completions.kwargs["reasoning_effort"] == "medium"


def test_effort_de_verification_configurable(monkeypatch):
    monkeypatch.setenv("GROQ_VERIFY_EFFORT", "high")
    client = _Client()
    monkeypatch.setattr(verification, "groq_client", client)
    verification._appel_verification(model="m", messages=[])
    assert client.completions.kwargs["reasoning_effort"] == "high"
