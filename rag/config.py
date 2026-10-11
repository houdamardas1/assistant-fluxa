"""Configuration : constantes, variables d'environnement, listes de roles et departements, politiques RBAC."""

import os
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()


INDEX_DIR = Path("data/index")


MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


# Modele du VERIFICATEUR : les quotas Groq sont par modele, un modele
# distinct separe les budgets (ex : GROQ_VERIFY_MODEL=openai/gpt-oss-20b).
GROQ_VERIFY_MODEL = os.getenv("GROQ_VERIFY_MODEL", GROQ_MODEL)


TOP_K_RETRIEVAL = 30


TOP_K_VERIFY = int(os.getenv("RAG_TOP_K_VERIFY", "15"))


# Caracteres de chaque extrait envoye au verificateur.
VERIFY_CHARS = int(os.getenv("RAG_VERIFY_CHARS", "1200"))


TOP_K_CONTEXT = 10


POIDS_FAISS = 0.50


POIDS_LEXICAL = 0.50


BONUS_ARTICLE_TITRE = 0.50


# Score minimal (somme des poids de mots-cles) pour qu'un departement soit
# considere comme detecte. Un seul mot-cle faible ne suffit pas.
SEUIL_DETECTION_DEPARTEMENT = 2


# Detection de REPLI par embeddings (quand aucun mot-cle n'a suffi) :
#   - similarite cosinus minimale entre la question et le meilleur
#     departement ;
#   - ecart minimal avec le 2e departement (sinon : ambigu -> None).
SEUIL_EMBEDDING_DEPARTEMENT = 0.45


MARGE_EMBEDDING_DEPARTEMENT = 0.05


DEBUG = os.getenv("RAG_DEBUG", "0") == "1"


# Par defaut, un departement qui ne contient QUE des textes reglementaires
# n'a pas de corpus reel. =1 retablit l'ancien comportement (demo sur lois).
ALLOW_PUBLIC_ONLY_DEPARTMENTS = (
    os.getenv("RAG_ALLOW_PUBLIC_ONLY_DEPARTMENTS", "0") == "1"
)


def _dbg(message: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {message}")


ROLES_DISPONIBLES = [
    "tous", "finance", "direction", "it", "rh",
    "commerce", "juridique", "marketing",
]


DEPARTEMENTS = [
    "direction", "finance", "it", "rh", "commerce", "juridique", "marketing",
]


LIBELLE_DEPARTEMENT = {
    "direction": "Direction",
    "finance": "Finance",
    "it": "IT",
    "rh": "Ressources humaines",
    "commerce": "Commerce",
    "juridique": "Juridique",
    "marketing": "Marketing",
}


# RBAC par ENTREPRISE (rapports de reporting externe deja indexes).
RBAC_POLICY = {
    "Auto_Nejma": {"tous", "direction"},
    "CDG_Capital": {"tous", "finance", "direction"},
    "Unimer": {"tous", "direction"},
    "Wafa_Assurance": {"tous", "finance", "direction"},
}


# RBAC par DEPARTEMENT (documents internes). Un chunk peut deroger avec son
# propre champ "access_roles".
DEPARTMENT_ACCESS_ROLES = {
    dept: {dept, "direction", "tous"} for dept in DEPARTEMENTS
}


ALIAS_ENTREPRISES = {
    "wafa": "Wafa_Assurance",
    "wafa assurance": "Wafa_Assurance",
    "cdg": "CDG_Capital",
    "cdg capital": "CDG_Capital",
    "unimer": "Unimer",
    "auto nejma": "Auto_Nejma",
    "nejma": "Auto_Nejma",
}


# Fichiers réglementaires TRANSVERSES : un meme texte de loi peut concerner
# plusieurs departements. L'ingestion ne pose qu'un seul "departement", ce
# qui provoque des faux refus (ex : le Code de commerce est utile au
# juridique autant qu'au commerce). Ce correctif est un PANSEMENT tant que
# l'ingestion n'ecrit pas un champ "departements" (liste). A retirer des
# qu'elle le fera.
FICHIERS_TRANSVERSES = {
    "Code_de_Commerce_Loi_15-95.pdf": {"juridique", "commerce"},
    "Loi_31-08_Protection_Consommateur.pdf": {"juridique", "commerce"},
}
