"""Classification d'intention : question d'entreprise ou generale, ENTREPRISE / GENERALE / ABSENTE."""

from .juridique import detect_reference_article
from .textutils import _norm, _regex_mots


# Termes SANS accents, testes sur _norm(query) avec frontieres de mots.
_RE_METIER = _regex_mots([
    "wafa", "wafa assurance", "cdg", "cdg capital", "unimer",
    "auto nejma", "nejma",
    "chiffre d'affaires", "chiffre affaires", "resultat net", "bilan",
    "dividende", "gouvernance", "rse", "esg",
    "primes emises", "primes acquises", "primes brutes emises",
    "produits des activites d'assurance", "produits d'assurance",
    "revenus d'assurance",
    "code du travail", "code de commerce", "code des obligations",
    "loi 31-08", "loi 65-99", "loi 15-95", "registre du commerce",
    "immatriculation", "conge annuel", "conges annuels", "conges payes",
    "jours de conge", "salaire",
    "recrutement", "reglement interieur",
    "clause abusive", "clauses abusives", "contrat de consommation",
    "protection du consommateur", "protection des consommateurs",
    "consommateur", "consommation",
    "politique de securite", "securite informatique", "dnssi",
    "directive de securite", "politique de securite informatique",
    "procedure commerciale", "conditions generales de vente",
    "charte graphique", "charte editoriale", "campagne marketing",
    "contrat cadre", "clause de confidentialite",
    "conseil d'administration", "conseil de surveillance",
    "assemblee generale", "administrateur", "administrateurs",
    "directeur general", "directrice generale", "comite de direction",
    "comite d'audit", "comex", "plan strategique",
    "orientations strategiques",
])


_RE_REGLEMENTAIRE = _regex_mots([
    "loi", "code", "article", "reglement", "directive", "decret",
    "circulaire", "texte juridique", "texte de loi", "selon la loi",
    "selon le code", "prevu par la loi", "prevu par le code",
])


_RE_INTERNE = _regex_mots([
    "notre entreprise", "notre societe", "l'entreprise", "la societe",
    "chez nous", "en interne", "au sein de l'entreprise",
    "au sein de notre", "politique interne", "procedure interne",
    "reglement interieur",
])


# Termes de gouvernance : sans prefixe de definition, plus probablement une
# reference a un document interne qu'a une question de cours. Tenter le RAG
# est sans risque (verification + classify_question retombent sur
# GENERALE/ABSENTE si rien n'est trouve).
_RE_GOUVERNANCE = _regex_mots([
    "politique", "procedure", "reglement", "consignes", "directive",
    "processus",
])


PREFIXES_GENERAUX = [
    "qu'est-ce qu'", "qu'est ce qu'", "qu'est-ce que", "qu'est ce que",
    "c'est quoi", "definis", "explique", "comment fonctionne",
    "quelle est la difference", "donne-moi la definition", "que signifie",
]


_INDICES_DOMAINE = [
    "entreprise", "societe", "contrat", "consommateur", "consommation",
    "travail", "commerce", "finance", "juridique", "rh",
    "ressources humaines", "marocain", "marocaine",
]


def detect_intent(query: str) -> str:
    """"entreprise" (tenter le RAG) ou "generale" (reponse sans RAG)."""
    q = _norm(query).strip()

    if _RE_METIER.search(q) or _RE_REGLEMENTAIRE.search(q) or _RE_INTERNE.search(q):
        return "entreprise"

    for prefix in PREFIXES_GENERAUX:
        if q.startswith(prefix):
            if any(h in q for h in _INDICES_DOMAINE):
                return "entreprise"
            return "generale"

    if _RE_GOUVERNANCE.search(q):
        return "entreprise"

    return "generale"


def classify_question(
    query: str, results: list, can_answer: bool, verify_error: bool
) -> str:
    """ENTREPRISE / GENERALE / ABSENTE."""
    has_strong_keyword = bool(_RE_METIER.search(_norm(query))) or bool(
        detect_reference_article(query)
    )
    has_good_score = bool(results) and results[0]["score"] >= 0.45

    if verify_error:
        if can_answer and has_strong_keyword:
            return "ENTREPRISE"
        return "ABSENTE" if has_strong_keyword else "GENERALE"

    if has_strong_keyword:
        return "ENTREPRISE" if can_answer else "ABSENTE"

    if can_answer and has_good_score:
        return "ENTREPRISE"

    return "GENERALE"
