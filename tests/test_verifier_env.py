import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "verifier_env", Path(__file__).resolve().parent.parent / "scripts" / "verifier_env.py")
ve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ve)

BON = {"ENVIRONMENT": "production", "DEBUG": "False", "SECRET_KEY": "a" * 48,
       "GROQ_API_KEY": "gsk_" + "Ab3" * 13, "POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p9Zq",
       "POSTGRES_DB": "d", "CORS_ORIGINS": '["https://fluxa.exemple.ma"]',
       "PUBLIC_API_URL": "https://api.exemple.ma"}


def test_env_prod_conforme():
    assert ve.verifier(BON) == []


def test_valeurs_exemple_refusees():
    pb = ve.verifier({**BON, "POSTGRES_PASSWORD": "CHANGE_ME", "SECRET_KEY": "your-secret-key-here" * 3})
    assert any("POSTGRES_PASSWORD" in p for p in pb)
    assert any("SECRET_KEY" in p for p in pb)


def test_debug_et_localhost_refuses_en_prod():
    pb = ve.verifier({**BON, "DEBUG": "True", "PUBLIC_API_URL": "http://localhost:8000"})
    assert any("DEBUG" in p for p in pb)
    assert any("localhost" in p for p in pb)


def test_dev_controle_minimal():
    assert ve.verifier({"ENVIRONMENT": "development", "GROQ_API_KEY": "gsk_" + "Ab3" * 13}) == []


def test_aucune_valeur_dans_les_messages():
    pb = ve.verifier({**BON, "POSTGRES_PASSWORD": "CHANGE_ME"})
    assert all("CHANGE_ME" not in p for p in pb)
