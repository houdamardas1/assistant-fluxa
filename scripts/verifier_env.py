"""Verifie qu'un fichier .env est utilisable pour un environnement.

Usage : python scripts/verifier_env.py [.env]
Sortie 0 = conforme ; 1 = problemes (noms de variables uniquement, jamais
les valeurs). Dev : controle minimal. Staging / production : secrets
presents et non factices, DEBUG coupe, SECRET_KEY longue ; production :
pas d'adresse localhost.
"""
import re
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"(changez-moi|change_me|your-secret-key|gsk_x{6,})", re.I)
REQUIS = ("SECRET_KEY", "GROQ_API_KEY", "POSTGRES_USER", "POSTGRES_PASSWORD",
          "POSTGRES_DB", "CORS_ORIGINS", "PUBLIC_API_URL")


def lire(chemin):
    env = {}
    for ligne in Path(chemin).read_text(encoding="utf-8-sig").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            k, v = ligne.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def verifier(env):
    """Retourne la liste des problemes (messages sans valeurs)."""
    cible = env.get("ENVIRONMENT", "development").lower()
    pb = []
    if PLACEHOLDER.search(env.get("GROQ_API_KEY", "")) or not env.get("GROQ_API_KEY"):
        pb.append("GROQ_API_KEY absente ou factice")
    if cible in ("development", "dev"):
        return pb
    for cle in REQUIS:
        if cle == "GROQ_API_KEY":
            continue  # deja controlee plus haut
        v = env.get(cle, "")
        if not v:
            pb.append(cle + " manquante")
        elif PLACEHOLDER.search(v):
            pb.append(cle + " contient encore une valeur d'exemple")
    if env.get("DEBUG", "").lower() in ("true", "1", "yes"):
        pb.append("DEBUG doit etre False hors developpement")
    if len(env.get("SECRET_KEY", "")) < 32:
        pb.append("SECRET_KEY trop courte (32 caracteres minimum)")
    if cible in ("production", "prod"):
        for cle in ("CORS_ORIGINS", "PUBLIC_API_URL"):
            if "localhost" in env.get(cle, "") or "127.0.0.1" in env.get(cle, ""):
                pb.append(cle + " pointe vers localhost en production")
    return pb


if __name__ == "__main__":
    chemin = sys.argv[1] if len(sys.argv) > 1 else ".env"
    problemes = verifier(lire(chemin))
    for p in problemes:
        print("PROBLEME :", p)
    print("Environnement conforme." if not problemes else "%d probleme(s)." % len(problemes))
    sys.exit(1 if problemes else 0)
