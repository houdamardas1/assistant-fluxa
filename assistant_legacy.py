#!/usr/bin/env python3
"""
Assistant RAG : recherche securisee (RBAC par role et par departement),
generation de reponse via Groq, citations des sources.

Principes :
  - le departement concerne est DETECTE automatiquement a partir de la
    question (detect_department) : l'utilisateur ne le selectionne plus ;
    si aucun mot-cle ne suffit, une detection de REPLI par embeddings
    (detect_department_embeddings) prend le relais ;
  - la securite reste portee par effective_allowed_roles() (par chunk) et
    par user_allowed_departments() (par departement detecte) ;
  - les reponses sont livrees en texte propre, sans markdown brut
    (nettoyer_reponse) ;
  - un refus d'acces produit un message professionnel adapte a la
    situation (message_refus_acces) ;
  - le perimetre comptable (social / consolide), la metrique litterale
    (chiffre d'affaires, primes emises...) et la temporalite sont des
    contraintes DURES verifiees en code avant le verificateur LLM ;
  - les questions comparatives (2+ indicateurs) sont decomposees en
    sous-questions (process_comparative_question) ;
  - un jeu de questions de reference peut etre rejoue (--eval) pour
    MESURER la qualite (reussite, retrieval, contenu, citations, refus
    d'acces, latence) et comparer deux versions (--eval-compare).

Variables d'environnement : GROQ_API_KEY, RAG_DEBUG=1,
RAG_USER_ROLE, RAG_USER_DEPARTMENT (forcage optionnel),
RAG_ALLOW_PUBLIC_ONLY_DEPARTMENTS=1.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv
from groq import Groq, RateLimitError
from sentence_transformers import SentenceTransformer

load_dotenv()


class QuotaError(Exception):
    """Quota Groq epuise (429) : ce n'est PAS une 'information absente'."""


# ============================================================================
# Configuration
# ============================================================================

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


def _init_groq() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        print(
            "Erreur : GROQ_API_KEY est absente.\n"
            "Ajoute la cle dans backend/.env :\n"
            "    GROQ_API_KEY=gsk_...",
            file=sys.stderr,
        )
        sys.exit(1)

    return Groq(api_key=api_key)


groq_client = _init_groq()


# ============================================================================
# Utilitaires texte
# ============================================================================

def _norm(text: str) -> str:
    """Minuscules, sans accents, apostrophes normalisees."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.lower().replace("’", "'")


def _regex_mots(termes: list) -> re.Pattern:
    """Regex a frontieres de mots pour une liste de termes SANS accents,
    a appliquer sur un texte passe par _norm()."""
    alternatives = "|".join(
        re.escape(t) for t in sorted(termes, key=len, reverse=True)
    )
    return re.compile(rf"\b(?:{alternatives})\b")


def nettoyer_markdown(text: str) -> str:
    """Retire le markdown brut (##, **, __, backticks) pour une reponse
    en texte propre. Les puces deviennent '- '."""
    text = text or ""
    text = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]*", "", text, flags=re.M)
    text = re.sub(r"^([ \t]*)[*•][ \t]+", r"\1- ", text, flags=re.M)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text, flags=re.S)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)\*(?=\S)(.+?)(?<=\S)\*(?!\w)", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normaliser_citations(text: str) -> str:
    """Crochets pleine largeur -> crochets ASCII."""
    return (text or "").replace("【", "[").replace("】", "]")


def nettoyer_reponse(text: str) -> str:
    """Normalisation finale de toute reponse generee par le LLM."""
    return nettoyer_markdown(normaliser_citations(text))


STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou",
    "que", "qui", "quoi", "quel", "quelle", "quels", "quelles",
    "est", "sont", "ete", "être", "avoir", "a", "au", "aux",
    "en", "dans", "sur", "pour", "par", "avec", "sans",
    "ce", "cette", "ces", "son", "sa", "ses", "leur", "leurs",
    "il", "elle", "ils", "elles", "on", "nous", "vous",
    "je", "tu", "me", "te", "se", "moi", "toi",
    "comment", "pourquoi", "quand", "où", "combien",
    "y", "n", "d", "l", "s", "t", "c", "j", "m",
}


def mots_utiles(texte: str, longueur_min: int = 3) -> list:
    return [
        w.lower()
        for w in re.findall(r"\b[\wÀ-ÿ']+\b", texte)
        if w.lower() not in STOPWORDS and len(w) >= longueur_min
    ]


# ============================================================================
# Matching tolerant (accents, singulier/pluriel, tiret/espace)
# ============================================================================

_CLASSES_ACCENTS = {"'": "['’]", "’": "['’]", "-": r"[-\s]"}

for _groupe in ("eéèêë", "aàâ", "iîï", "oô", "uùû", "cç"):
    for _ch in _groupe:
        _CLASSES_ACCENTS[_ch] = f"[{_groupe}]"


def _motif_terme(terme: str) -> re.Pattern:
    """Compile un terme metier en regex tolerante : accents optionnels,
    singulier/pluriel de chaque mot, espacement irregulier (survit aux
    artefacts d'extraction PDF comme "Primes Emise")."""
    parties = []

    for mot in terme.split():
        base = mot.rstrip("sS") or mot
        parties.append(
            "".join(
                _CLASSES_ACCENTS.get(c.lower(), re.escape(c)) for c in base
            )
            + "s?"
        )

    return re.compile(r"\s+".join(parties), flags=re.IGNORECASE)


_CACHE_MOTIFS: dict = {}


def _motif_terme_cache(terme: str) -> re.Pattern:
    motif = _CACHE_MOTIFS.get(terme)
    if motif is None:
        motif = _motif_terme(terme)
        _CACHE_MOTIFS[terme] = motif
    return motif


def contient_terme(content: str, terme: str) -> bool:
    return bool(_motif_terme_cache(terme).search(content))


def position_terme(content: str, terme: str):
    return _motif_terme_cache(terme).search(content)


def contient_un_des_termes(content: str, termes: list) -> bool:
    return any(contient_terme(content, t) for t in termes)


# ============================================================================
# Familles metier (retrieval) : volontairement larges
# ============================================================================

FAMILLES_METIER = {
    "resultat_net": {
        "declencheurs": [
            r"r[ée]sultat\s+net", r"b[ée]n[ée]fice\s+net",
            r"profit\s+net", r"net\s+income", r"net\s+profit",
        ],
        "termes": [
            "résultat net", "bénéfice net", "profit net",
            "net income", "net profit",
        ],
        "termes_sectoriels": {},
    },
    "resultat_vie": {
        "declencheurs": [
            r"r[ée]sultat\s+vie", r"r[ée]sultat\s+de\s+la\s+vie",
        ],
        "termes": ["résultat Vie", "résultat de la Vie"],
        "termes_sectoriels": {
            "assurance": ["résultat Vie", "résultat de la Vie"],
        },
    },
    "resultat_non_vie": {
        "declencheurs": [
            r"r[ée]sultat\s+non[- ]?vie",
            r"r[ée]sultat\s+de\s+la\s+non[- ]?vie",
        ],
        "termes": ["résultat Non-Vie", "résultat de la Non-Vie"],
        "termes_sectoriels": {
            "assurance": ["résultat Non-Vie", "résultat de la Non-Vie"],
        },
    },
    "chiffre_affaires": {
        "declencheurs": [
            r"chiffre\s+d['’]?\s*affaires",
            r"\bca\b",
            r"\brevenus?\b",
            r"turnover",
            r"primes?\s+(?:émises?|emises?|acquises?|brutes?)",
            r"produits?\s+des?\s+activit[ée]s?\s+d['’]?assurance",
        ],
        "termes": ["chiffre d'affaires", "chiffre affaires", "revenus"],
        "termes_sectoriels": {
            "assurance": [
                "primes émises", "primes acquises", "primes brutes émises",
                "produits des activités d'assurance",
                "produits d'assurance", "revenus d'assurance",
            ],
        },
    },
}


def detect_famille(query: str) -> str | None:
    q = query.lower()

    for nom, conf in FAMILLES_METIER.items():
        if any(re.search(p, q, flags=re.IGNORECASE) for p in conf["declencheurs"]):
            return nom

    return None


def secteur_est_assurance(secteur) -> bool:
    return bool(secteur) and "assurance" in secteur.lower()


def termes_generiques_famille(famille: str | None) -> list:
    if not famille:
        return []
    return list(FAMILLES_METIER.get(famille, {}).get("termes", []))


def termes_sectoriels_famille(famille: str | None, secteur) -> list:
    if not famille or not secteur_est_assurance(secteur):
        return []
    return list(
        FAMILLES_METIER.get(famille, {})
        .get("termes_sectoriels", {})
        .get("assurance", [])
    )


def terme_generique_present(famille: str | None, content: str) -> bool:
    return contient_un_des_termes(content, termes_generiques_famille(famille))


def terme_sectoriel_present(famille: str | None, secteur, content: str) -> bool:
    """Equivalent sectoriel present ET terme generique absent."""
    if terme_generique_present(famille, content):
        return False
    return contient_un_des_termes(
        content, termes_sectoriels_famille(famille, secteur)
    )


# Filiales / devises etrangeres (penalite sauf si la question les vise).
# Termes sans accents, testes sur du texte passe par _norm().
_RE_FILIALES = _regex_mots([
    "cote d'ivoire", "cameroun", "senegal", "gabon", "egypte", "egypt",
    "tunisie", "delta insurance", "delta life", "wafa life insurance",
])
_RE_DEVISES = _regex_mots(["mfcfa", "megp", "fcfa", "mtnd", "meur", "musd"])


# ============================================================================
# Perimetre comptable (social / consolide) : contrainte DURE
# ============================================================================

_RE_ASK_SOCIAL = re.compile(r"\bsocial(?:e|es)?\b|\bsociaux\b", re.IGNORECASE)

_RE_ASK_CONSOLIDE = re.compile(
    r"\bconsolid[ée]e?s?\b|\bconsolidation\b|\brnpg\b|\bpart\s+du\s+groupe\b",
    re.IGNORECASE,
)

# Termes sans accents, testes sur _norm(content).
_TERMES_CHUNK_CONSOLIDE = [
    "activite consolidee", "comptes consolides", "resultats consolides",
    "consolide ifrs", "revenus d'assurance consolides",
    "primes emises du groupe", "ensemble consolide",
    "part du groupe", "rnpg",
]
_TERMES_CHUNK_SOCIAL = [
    "resultats sociaux", "comptes sociaux", "compte social",
    "etats financiers sociaux",
]

_SCOPE_LOCAL = {
    "social": [
        r"r[ée]sultats?\s+sociaux", r"comptes?\s+sociaux",
        r"[ée]tats?\s+financiers?\s+sociaux", r"exercice\s+social",
        r"r[ée]sultat\s+social",
    ],
    "consolide": [
        r"r[ée]sultats?\s+consolid[ée]s?", r"comptes?\s+consolid[ée]s?",
        r"[ée]tats?\s+financiers?\s+consolid[ée]s?",
        r"ensemble\s+consolid[ée]",
        r"p[ée]rim[eè]tre\s+de\s+consolidation",
    ],
}


def detect_scope(query: str) -> str | None:
    """Perimetre explicitement demande ("consolide", "social") ou None.
    "groupe" seul n'est volontairement PAS un signal (c'est souvent juste
    le nom de l'entreprise)."""
    if _RE_ASK_CONSOLIDE.search(query):
        return "consolide"
    if _RE_ASK_SOCIAL.search(query):
        return "social"
    return None


def detect_chunk_scope(content: str) -> str | None:
    c = _norm(content)

    if any(t in c for t in _TERMES_CHUNK_CONSOLIDE):
        return "consolide"
    if any(t in c for t in _TERMES_CHUNK_SOCIAL):
        return "social"
    return None


def _scope_local(content: str, scope: str) -> bool:
    return any(
        re.search(p, content or "", flags=re.IGNORECASE)
        for p in _SCOPE_LOCAL.get(scope, [])
    )


def scope_incompatible(query: str, content: str) -> bool:
    """Rejette un chunk dont le perimetre contredit celui demande, ou dont
    le perimetre n'est pas detectable alors qu'il est explicitement demande."""
    scope_demande = detect_scope(query)

    if scope_demande is None:
        return False

    scope_chunk = detect_chunk_scope(content)

    if scope_chunk == scope_demande:
        return False

    if scope_chunk is None and _scope_local(content, scope_demande):
        return False

    return True


# ============================================================================
# Metrique financiere litterale
# ============================================================================
#
# detect_famille() regroupe CA / primes emises / revenus d'assurance pour le
# RETRIEVAL. detect_metric() identifie l'indicateur LITTERAL demande, pour
# interdire qu'un extrait "primes emises" serve de preuve a une question sur
# le "chiffre d'affaires" (et inversement).

_PATTERNS_METRIC = {
    "chiffre_affaires": r"chiffre\s+d['’]?\s*affaires",
    "primes_emises": r"primes?\s+(?:émises?|emises?|acquises?|brutes?)",
    "revenus_assurance": r"revenus?\s+d['’]?\s*assurance",
    "produits_activites_assurance":
        r"produits?\s+des?\s+activit[ée]s?\s+d['’]?\s*assurance",
    "resultat_vie": r"(?:résultat|resultat)\s+(?:de\s+la\s+)?vie\b",
    "resultat_non_vie": r"(?:résultat|resultat)\s+(?:de\s+la\s+)?non[- ]?vie\b",
    "resultat_net": r"(?:résultat|resultat)\s+net",
}


def detect_metric(query: str) -> str | None:
    q = query.lower()

    for nom, pattern in _PATTERNS_METRIC.items():
        if re.search(pattern, q, flags=re.IGNORECASE):
            return nom

    return None


def metriques_presentes(content: str) -> set:
    c = content.lower()
    return {
        nom
        for nom, pattern in _PATTERNS_METRIC.items()
        if re.search(pattern, c, flags=re.IGNORECASE)
    }


def _normaliser_texte_preuve(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _segment_apres_metrique(
    text: str, metric: str, fin_match: int, longueur: int = 250
) -> str:
    """Segment qui SUIT le terme de la metrique, coupe au premier AUTRE
    indicateur financier : evite de lire le montant d'un indicateur voisin
    (ex: "Resultat net ... 943 MDH" colle a "chiffre d'affaires")."""
    segment = (text or "")[fin_match:fin_match + longueur]
    coupe = len(segment)

    for autre, pattern in _PATTERNS_METRIC.items():
        if autre == metric:
            continue
        n = re.search(pattern, segment, flags=re.IGNORECASE)
        if n:
            coupe = min(coupe, n.start())

    return segment[:coupe]


_RE_VALEUR = re.compile(
    r"(?:\d[\d\s.,]*\s*(?:mmdh|mdh|mmad|kmad|mad|dh|dirhams?|"
    r"millions?|milliards?)|"
    r"(?:s['’]?établit|s['’]?eleve|s['’]?élève|ressort)\s+(?:à|a)\s+\d)",
    flags=re.IGNORECASE,
)


def _preuve_metric_locale(content: str, metric: str) -> bool:
    """La metrique demandee est-elle suivie, dans un segment local, d'une
    valeur chiffree exploitable ?

    Rejets : serie pluriannuelle (3 annees distinctes ou plus), tableau PDF
    casse (5 nombres colles ou plus), meme valeur repetee 3 fois ou plus.
    """
    pattern = _PATTERNS_METRIC.get(metric)

    if not pattern:
        return False

    texte = content or ""

    for m in re.finditer(pattern, texte, flags=re.IGNORECASE):

        segment = _normaliser_texte_preuve(
            _segment_apres_metrique(texte, metric, m.end())
        )

        if not _RE_VALEUR.search(segment):
            continue

        if len(set(re.findall(r"\b20\d{2}\b", segment))) >= 3:
            continue

        if len(re.findall(r"\b\d[\d.,]{2,}\b", segment)) >= 5:
            continue

        valeurs = [
            v.replace(" ", "").replace(",", ".").rstrip(".")
            for v in re.findall(
                r"(\d[\d\s.,]*)\s*(?:mmdh|mdh|mmad|kmad|mad|dh)",
                segment,
                flags=re.IGNORECASE,
            )
        ]

        if any(valeurs.count(v) >= 3 for v in set(valeurs)):
            continue

        return True

    return False


def metric_incompatible(query: str, content: str) -> bool:
    metric = detect_metric(query)
    if metric is None:
        return False
    if _preuve_metric_locale(content, metric):
        return False
    # Le chiffre d'affaires reste STRICT (primes emises != CA).
    if metric == "chiffre_affaires":
        return True
    # Autres metriques : sans valeur lisible (tableau PDF), on n'elimine
    # que si la metrique litterale est ABSENTE du chunk. Sinon le
    # verificateur tranche.
    return metric not in metriques_presentes(content)


# ============================================================================
# Questions comparatives (2+ indicateurs)
# ============================================================================

_LIBELLE_METRIC = {
    "chiffre_affaires": "chiffre d'affaires",
    "resultat_vie": "résultat Vie",
    "resultat_non_vie": "résultat Non-Vie",
    "primes_emises": "primes émises",
    "revenus_assurance": "revenus d'assurance",
    "produits_activites_assurance": "produits des activités d'assurance",
    "resultat_net": "résultat net",
}

_LIBELLE_SCOPE = {"social": "social", "consolide": "consolidé", None: ""}


def detect_intents(query: str) -> list[dict]:
    """Liste des indicateurs distincts demandes, chacun avec son perimetre
    (ou None). Une question simple ne produit qu'UN element."""
    q = query.lower()
    annees = re.findall(r"\b(?:19|20)\d{2}\b", q)
    year = int(annees[0]) if annees else None
    intents: list[dict] = []

    def add(metric, scope):
        intents.append({"metric": metric, "scope": scope, "year": year})

    soc = r"\b(?:social|sociale|sociaux|sociales)\b"
    cons = r"\b(?:consolid[eé]e?s?|consolidation)\b"
    ca = r"chiffre\s+d['’]?\s*affaires"
    prime = r"primes?\s+(?:émises?|emises?)"
    revenus = r"revenus?\s+d['’]?\s*assurance"
    rnet = r"(?:résultat|resultat)\s+net"

    if re.search(rf"{ca}.*?{soc}", q):
        add("chiffre_affaires", "social")
    elif re.search(rf"{ca}.*?{cons}", q):
        add("chiffre_affaires", "consolide")
    elif re.search(ca, q):
        add("chiffre_affaires", None)

    if re.search(rf"{prime}.*?(?:{cons}|\bgroupe\b)", q):
        add("primes_emises", "consolide")
    elif re.search(prime, q):
        add("primes_emises", None)

    if re.search(rf"{revenus}.*?{cons}", q):
        add("revenus_assurance", "consolide")
    elif re.search(revenus, q):
        add("revenus_assurance", None)

    if re.search(r"(?:résultat|resultat)\s+(?:de\s+la\s+)?vie\b", q):
        add("resultat_vie", None)

    if re.search(r"(?:résultat|resultat)\s+(?:de\s+la\s+)?non[- ]?vie\b", q):
        add("resultat_non_vie", None)

    if re.search(rf"{rnet}.*?{soc}", q):
        add("resultat_net", "social")
    elif re.search(rf"{rnet}.*?(?:{cons}|\brnpg\b)", q):
        add("resultat_net", "consolide")
    elif re.search(rnet, q):
        add("resultat_net", None)

    return intents


# Formulation grammaticale par indicateur : (debut de question, genre+nombre).
_GRAMMAIRE_METRIC = {
    "chiffre_affaires": ("Quel est le", "ms"),
    "resultat_vie": ("Quel est le", "ms"),
    "resultat_non_vie": ("Quel est le", "ms"),
    "resultat_net": ("Quel est le", "ms"),
    "primes_emises": ("Quelles sont les", "fp"),
    "revenus_assurance": ("Quels sont les", "mp"),
    "produits_activites_assurance": ("Quels sont les", "mp"),
}

_ACCORD_SCOPE = {
    "social": {"ms": "social", "mp": "sociaux", "fs": "sociale", "fp": "sociales"},
    "consolide": {
        "ms": "consolidé", "mp": "consolidés",
        "fs": "consolidée", "fp": "consolidées",
    },
}


def build_subquery(entreprise_display: str, intent: dict) -> str:
    """Question simple et non ambigue pour UN seul intent."""
    label = _LIBELLE_METRIC.get(intent["metric"], intent["metric"])
    debut, accord = _GRAMMAIRE_METRIC.get(
        intent["metric"], ("Quel est le", "ms")
    )
    scope = _ACCORD_SCOPE.get(intent.get("scope") or "", {}).get(accord)
    scope_part = f" {scope}" if scope else ""
    year_part = f" en {intent['year']}" if intent.get("year") else ""
    ent_part = f" de {entreprise_display}" if entreprise_display else ""

    return f"{debut} {label}{scope_part}{ent_part}{year_part} ?"


RE_MONTANT = re.compile(
    r"([\d][\d\s\u00a0.,]*)\s*"
    r"(MMDH|MDH|KMAD|MMAD|MAD|MFCFA|MEGP|FCFA|MTND|MEUR|MUSD)\b",
    flags=re.IGNORECASE,
)


def extraire_montant(texte: str):
    """(valeur, unite) du premier montant suivi d'une unite explicite, ou
    None. Un nombre nu n'est jamais interprete comme un montant."""
    m = RE_MONTANT.search(texte)

    if not m:
        return None

    brut = m.group(1).strip().replace("\u00a0", " ").replace(" ", "")
    brut = brut.replace(",", ".")

    if brut.count(".") > 1:
        entier, _, decimal = brut.rpartition(".")
        brut = entier.replace(".", "") + "." + decimal

    try:
        valeur = float(brut)
    except ValueError:
        return None

    return valeur, m.group(2).upper()


def extraire_montant_source(rag_results: list, metric: str | None):
    """Montant lu dans le CONTENU des chunks valides (pas dans le texte du
    LLM), uniquement apres le terme de la metrique et avant le prochain
    autre indicateur ; les series pluriannuelles sont ignorees."""
    pattern = _PATTERNS_METRIC.get(metric or "")

    if not pattern:
        return None

    for r in rag_results:
        texte = r.get("content", "") or ""

        for m in re.finditer(pattern, texte, flags=re.IGNORECASE):
            segment = _segment_apres_metrique(texte, metric, m.end())

            if len(set(re.findall(r"\b20\d{2}\b", segment))) >= 3:
                continue

            montant = extraire_montant(segment)

            if montant:
                return montant

    return None


# ============================================================================
# References juridiques
# ============================================================================

RE_REFERENCE_ARTICLE = re.compile(
    r"\b(?:article|art\.?)\s*(\d+)\b", flags=re.IGNORECASE
)

RE_CONTEXTE_RENVOI = re.compile(
    r"(?:de|des|du|aux?|à|a|par|dans|selon|pour|sous|"
    r"vis[ée]e?s?|pr[ée]vue?s?|fix[ée]e?s?|mentionn[ée]e?s?|"
    r"conform[ée]ment|dispositions?|termes?|application)"
    r"\s+l?['’]?\s*$",
    flags=re.IGNORECASE,
)


def detect_reference_article(query: str) -> str | None:
    match = RE_REFERENCE_ARTICLE.search(query)
    return match.group(1) if match else None


def est_titre_article(content: str, numero: str) -> bool:
    """Le chunk contient le TITRE de l'article (son texte), pas un renvoi."""
    if not numero:
        return False

    motif = re.compile(rf"\barticles?\s+{re.escape(numero)}\b", re.IGNORECASE)

    for m in motif.finditer(content):
        debut_ligne = content.rfind("\n", 0, m.start()) + 1

        if content[debut_ligne:m.start()].strip() == "":
            return True

        avant = content[max(0, m.start() - 40):m.start()]

        if not RE_CONTEXTE_RENVOI.search(avant):
            return True

    return False


def est_renvoi_article(content: str, numero: str) -> bool:
    if not numero:
        return False
    return bool(
        re.search(rf"\barticles?\s+{re.escape(numero)}\b", content, re.IGNORECASE)
    )


# ============================================================================
# Temporalite
# ============================================================================

TEMPORAL_PLANNED_PATTERNS = [
    r"\bpr[ée]vu(?:e|s|es)?\b", r"\bpr[ée]voit\b", r"\bpr[ée]vision(?:s)?\b",
    r"\bobjectif(?:s)?\b", r"\bpoursuivr(?:a|ont)\b",
    r"\bprendr(?:a|ont)\b", r"\bser(?:a|ont|aient)\b",
    r"\bdevr(?:a|ont|aient)\b",
    r"\benvisage(?:r|ant|ait|aient)?\b", r"\bplanifi(?:é|ée|és|ées|e|ent)\b",
    r"\b[àa] venir\b",
]

TEMPORAL_ACTUAL_PATTERNS = [
    r"\bau\s+31\s+(?:décembre|decembre)\s+{year}\b",
    r"\bexercice\s+{year}\b",
    r"\brésultats?\s+(?:annuels?\s+)?(?:de\s+)?{year}\b",
    r"\br[ée]sultats?\s+(?:sociaux|consolid[ée]s?)\b",
    r"\bs'établit\b", r"\bs'[ée]l[èe]ve\b", r"\bressort\s+[àa]\b",
    r"\ba\s+(?:augment|progress|diminu)[ée]\b",
    r"\ba\s+r[ée]alis[ée]\b",
]


def _report_year(chunk: dict) -> int | None:
    years = re.findall(r"\b20\d{2}\b", chunk.get("fichier_source", ""))
    return int(years[-1]) if years else None


def detect_temporal_requirement(query: str) -> tuple[int | None, str]:
    """(annee, mode) avec mode in {"any", "actual", "planned"}. Pour une
    annee passee, le mode par defaut est "actual" : un plan pour cette
    annee ne prouve pas un resultat realise."""
    years = re.findall(r"\b(?:19|20)\d{2}\b", query)
    year = int(years[0]) if years else None
    q = query.lower()

    if any(re.search(p, q, flags=re.IGNORECASE) for p in TEMPORAL_PLANNED_PATTERNS):
        return year, "planned"

    return year, "actual" if year else "any"


def classify_chunk_temporal(chunk: dict, requested_year: int | None) -> str:
    """"actual", "planned" ou "unknown" pour une annee donnee."""
    if requested_year is None:
        return "unknown"

    content = chunk.get("content", "")
    text = f"{content} {chunk.get('fichier_source', '')}"

    if not re.search(rf"\b{requested_year}\b", text):
        return "unknown"

    if any(re.search(p, content, flags=re.IGNORECASE)
           for p in TEMPORAL_PLANNED_PATTERNS):
        return "planned"

    actual = [p.format(year=requested_year) for p in TEMPORAL_ACTUAL_PATTERNS]

    if any(re.search(p, content, flags=re.IGNORECASE) for p in actual):
        return "actual"

    if _report_year(chunk) == requested_year:
        return "actual"

    return "unknown"


def temporal_incompatible(query: str, chunk: dict) -> bool:
    year, mode = detect_temporal_requirement(query)

    if year is None or mode == "any":
        return False

    status = classify_chunk_temporal(chunk, year)
    chunk["_temporal_status"] = status

    if mode == "actual":
        return status in {"planned", "unknown"}

    return status == "unknown"


# ============================================================================
# Index et RBAC
# ============================================================================

def load_index():
    index = faiss.read_index(str(INDEX_DIR / "index.faiss"))

    with open(INDEX_DIR / "metadata.json", "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return index, metadata


def effective_allowed_roles(chunk: dict) -> set:
    """Roles autorises a lire un chunk (RBAC strict : les textes
    reglementaires suivent les memes regles que les documents d'entreprise).

    Priorite : "access_roles" explicite du chunk > politique par
    DEPARTEMENT > politique par ENTREPRISE > allowed_roles historiques.
    Ne lit JAMAIS le champ "departements" (pertinence d'onglet, pas droit).

    Cas particulier : les fichiers TRANSVERSES (FICHIERS_TRANSVERSES),
    qu'un seul departement ne peut pas couvrir, sont accessibles a tous
    les departements listes plus "direction" et "tous". C'est un correctif
    d'ingestion : a retirer quand le champ "departements" (liste) sera pose.
    """
    transverse = FICHIERS_TRANSVERSES.get(chunk.get("fichier_source"))
    if transverse:
        return set(transverse) | {"direction", "tous"}

    access_roles = chunk.get("access_roles")
    if access_roles:
        return set(access_roles)

    departement = chunk.get("departement")
    if departement in DEPARTMENT_ACCESS_ROLES:
        return set(DEPARTMENT_ACCESS_ROLES[departement])

    ent = chunk.get("entreprise")
    if ent in RBAC_POLICY:
        return set(RBAC_POLICY[ent])

    return set(chunk.get("allowed_roles", []))


def est_accessible(chunk: dict, user_role: str) -> bool:
    return user_role in effective_allowed_roles(chunk)


# ============================================================================
# Departements : acces, perimetre et DETECTION AUTOMATIQUE
# ============================================================================

def user_allowed_departments(user_role: str) -> set:
    """Departements sur lesquels ce role peut poser des questions.
    "tous" et "direction" : vue transverse ; un role departemental : son
    propre departement. Ce n'est pas un second systeme RBAC : chaque chunk
    reste soumis a effective_allowed_roles()."""
    if user_role in ("tous", "direction"):
        return set(DEPARTEMENTS)

    if user_role in DEPARTEMENTS:
        return {user_role}

    return set()


def department_access_denied(user_role: str, departement: str | None) -> bool:
    if not departement or departement not in DEPARTEMENTS:
        return False
    return departement not in user_allowed_departments(user_role)


def departements_du_chunk(chunk: dict) -> set:
    """Departements auxquels un chunk est rattache ("departements" multi,
    puis "departement"). Sert au perimetre d'onglet, pas au controle
    d'acces."""
    deps = chunk.get("departements")

    if isinstance(deps, list) and deps:
        valides = {d for d in deps if d in DEPARTEMENTS}
        if valides:
            return valides

    dep = chunk.get("departement")
    return {dep} if dep in DEPARTEMENTS else set()


def chunk_matches_department(chunk: dict, departement: str) -> bool:
    """Filtre de PERIMETRE (pas d'autorisation). Les textes reglementaires
    restent visibles partout ; un chunk d'entreprise non classifie est
    rattache par convention a Finance et Direction."""
    if chunk.get("type_document", "entreprise") == "public_reglementaire":
        return True

    deps = departements_du_chunk(chunk)

    if deps:
        return departement in deps

    if departement in ("finance", "direction"):
        return chunk.get("type_document", "entreprise") == "entreprise"

    return False


def departement_a_corpus_reel(metadata: list, dept: str) -> bool:
    """Au moins un document REEL du departement : ni synthetique, ni texte
    reglementaire (sauf RAG_ALLOW_PUBLIC_ONLY_DEPARTMENTS=1)."""
    for chunk in metadata:
        if dept not in departements_du_chunk(chunk):
            continue
        if chunk.get("is_synthetic"):
            continue
        if (
            not ALLOW_PUBLIC_ONLY_DEPARTMENTS
            and chunk.get("type_document", "entreprise") == "public_reglementaire"
        ):
            continue
        return True
    return False


# Mots-cles par departement : (regex SANS accents, poids). Poids 2 = signal
# fort ; poids 1 = signal faible (ne suffit pas seul, voir
# SEUIL_DETECTION_DEPARTEMENT).
_MOTS_CLES_DEPARTEMENT = {
    "finance": [
        (r"chiffres? d'affaires", 2), (r"resultats? net", 2),
        (r"bilans?", 2), (r"dividendes?", 2), (r"rnpg", 2),
        (r"primes? (?:emises?|acquises?|brutes?)", 2),
        (r"revenus? d'assurance", 2),
        (r"produits? des activites d'assurance", 2),
        (r"resultats? (?:sociaux|consolides?)", 2),
        (r"comptes? (?:sociaux|consolides?)", 2),
        (r"etats? financiers?", 2), (r"fonds propres", 2),
        (r"tresorerie", 2), (r"rentabilite", 2),
        (r"resultat (?:de la )?(?:non[- ])?vie", 2),
        (r"budgets?", 1), (r"charges?", 1), (r"marges?", 1),
        (r"comptabilite", 1), (r"investissements?", 1),
    ],
    "direction": [
        (r"conseil d'administration", 2), (r"conseil de surveillance", 2),
        (r"assemblee generale", 2), (r"administrateurs?", 2),
        (r"directeur general", 2), (r"directrice generale", 2),
        (r"comite de direction", 2), (r"comite d'audit", 2),
        (r"comex", 2), (r"plan strategique", 2),
        (r"orientations? strategiques?", 2), (r"gouvernance", 2),
        (r"strategie", 1), (r"rse", 1), (r"esg", 1),
    ],
    "it": [
        (r"securite informatique", 2), (r"politique de securite", 2),
        (r"directive de securite", 2), (r"dnssi", 2),
        (r"systemes? d'information", 2), (r"cybersecurite", 2),
        (r"mots? de passe", 2), (r"serveurs?", 2), (r"sauvegardes?", 2),
        (r"incidents? de securite", 2), (r"infrastructure", 2),
        (r"reseau informatique", 2),
        (r"securite", 1), (r"logiciels?", 1), (r"application", 1),
    ],
    "rh": [
        (r"conges? (?:annuels?|payes?)", 2), (r"salaires?", 2),
        (r"recrutements?", 2), (r"code du travail", 2),
        (r"reglement interieur", 2), (r"contrats? de travail", 2),
        (r"paie", 2), (r"licenciements?", 2), (r"demissions?", 2),
        (r"remunerations?", 2), (r"ressources humaines", 2),
        (r"periode d'essai", 2),
        (r"formations?", 1), (r"collaborateurs?", 1), (r"salaries?", 1),
        (r"employes?", 1), (r"absences?", 1),
    ],
    "commerce": [
        (r"procedures? commerciales?", 2),
        (r"conditions generales de vente", 2), (r"devis", 2),
        (r"prospects?", 2), (r"offres? commerciales?", 2),
        (r"tarifs?", 2), (r"commandes?", 2), (r"remises?", 2),
        (r"clients?", 1), (r"ventes?", 1),
    ],
    "juridique": [
        (r"contrats? cadres?", 2), (r"clauses? abusives?", 2),
        (r"clause de confidentialite", 2), (r"code de commerce", 2),
        (r"code des obligations", 2), (r"registre du commerce", 2),
        (r"immatriculation", 2), (r"protection des? consommateurs?", 2),
        (r"contrats? de consommation", 2), (r"contentieux", 2),
        (r"conformite juridique", 2), (r"loi \d+-\d+", 2),
        (r"clauses?", 1), (r"lois?", 1), (r"juridique", 1),
        (r"contrats?", 1), (r"articles? \d+", 1),
    ],
    "marketing": [
        (r"charte graphique", 2), (r"charte editoriale", 2),
        (r"campagnes? marketing", 2), (r"reseaux sociaux", 2),
        (r"newsletter", 2), (r"image de marque", 2),
        (r"identite visuelle", 2),
        (r"marketing", 1), (r"communication", 1), (r"marque", 1),
        (r"publicite", 1),
    ],
}

_RE_DEPARTEMENT = {
    dept: [(re.compile(rf"\b(?:{p})\b"), poids) for p, poids in termes]
    for dept, termes in _MOTS_CLES_DEPARTEMENT.items()
}


def detect_department(query: str, user_role: str | None = None) -> str | None:
    """Detecte le departement concerne par la question.

    Score = somme des poids des mots-cles du departement. Retourne None si
    aucun departement n'atteint SEUIL_DETECTION_DEPARTEMENT (aucun filtre
    n'est alors applique). En cas d'egalite, le departement du role de
    l'utilisateur departage ; sinon None.
    """
    q = _norm(query)

    scores = {
        dept: sum(poids for rx, poids in regles if rx.search(q))
        for dept, regles in _RE_DEPARTEMENT.items()
    }

    meilleur = max(scores.values())

    if meilleur < SEUIL_DETECTION_DEPARTEMENT:
        return None

    tetes = [d for d, s in scores.items() if s == meilleur]

    if len(tetes) == 1:
        return tetes[0]

    if user_role in tetes:
        return user_role

    return None


# ----------------------------------------------------------------------------
# Detection de REPLI par embeddings (quand les mots-cles ne suffisent pas)
# ----------------------------------------------------------------------------
#
# Chaque departement est decrit par quelques phrases-types (formulations
# naturelles, sans dependre de mots-cles exacts). La question est comparee
# a ces phrases avec le MEME modele d'embeddings que le retrieval (aucun
# modele supplementaire). Le departement n'est retenu que si :
#   - la meilleure similarite atteint SEUIL_EMBEDDING_DEPARTEMENT ;
#   - l'ecart avec le 2e departement atteint MARGE_EMBEDDING_DEPARTEMENT
#     (sinon la question est ambigue : on prefere ne rien detecter).
# Cette detection ne sert QUE de perimetre/contexte : la securite reste
# portee par effective_allowed_roles() sur chaque chunk.

_PHRASES_DEPARTEMENT = {
    "finance": [
        "Quel est le chiffre d'affaires et le résultat net de l'entreprise ?",
        "Quels sont les états financiers, le bilan et la trésorerie ?",
        "Comment évolue la rentabilité, les marges et les dividendes ?",
        "Quel est le budget prévu et le niveau des charges ?",
    ],
    "direction": [
        "Quelles sont les orientations stratégiques décidées par la direction générale ?",
        "Que dit le conseil d'administration sur la gouvernance de l'entreprise ?",
        "Quelles décisions ont été prises en comité de direction ?",
        "Quel est le plan stratégique et la vision du groupe ?",
    ],
    "it": [
        "Quelle est la politique de sécurité informatique de l'entreprise ?",
        "Comment fonctionne le système d'information, les serveurs et les sauvegardes ?",
        "Que faire en cas d'incident de sécurité ou de panne du réseau ?",
        "Comment gérer les accès, les mots de passe et les logiciels ?",
    ],
    "rh": [
        "Combien de jours de congé ai-je le droit de prendre ?",
        "Comment se déroule le recrutement, la paie et la rémunération des salariés ?",
        "Quelles sont les règles du contrat de travail, de la période d'essai et des absences ?",
        "Quelles formations et quels avantages sont offerts aux collaborateurs ?",
    ],
    "commerce": [
        "Quelle est la procédure pour établir un devis ou traiter une commande client ?",
        "Quelles sont les conditions de vente, les tarifs et les remises accordées ?",
        "Comment suivre les prospects et les offres commerciales ?",
        "Comment fidéliser les clients et développer les ventes ?",
    ],
    "juridique": [
        "Que prévoit la loi ou le code concernant les obligations de l'entreprise ?",
        "Quelles clauses du contrat sont abusives ou nécessitent une validation juridique ?",
        "Quelle est la réglementation applicable en cas de litige ou de contentieux ?",
        "Quelles sont les obligations de conformité et de confidentialité ?",
    ],
    "marketing": [
        "Quelle est la charte graphique et l'identité visuelle de la marque ?",
        "Comment préparer une campagne de communication ou de publicité ?",
        "Que publier sur les réseaux sociaux et dans la newsletter ?",
        "Comment renforcer l'image de marque et la notoriété de l'entreprise ?",
    ],
}

# Cache : (matrice normalisee des phrases, departement de chaque ligne).
_CACHE_PROTOTYPES: dict = {}


def _prototypes_departement(model):
    """Embeddings normalises des phrases-types, calcules une seule fois
    par modele."""
    cle = id(model)
    cache = _CACHE_PROTOTYPES.get(cle)

    if cache is not None:
        return cache

    phrases, depts = [], []

    for dept, liste in _PHRASES_DEPARTEMENT.items():
        for p in liste:
            phrases.append(p)
            depts.append(dept)

    matrice = model.encode(phrases, convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(matrice)

    _CACHE_PROTOTYPES[cle] = (matrice, depts)
    return _CACHE_PROTOTYPES[cle]


def detect_department_embeddings(
    query: str, model, user_role: str | None = None
) -> str | None:
    """Detection de repli : departement le plus proche de la question par
    similarite d'embeddings, ou None si le signal est trop faible ou
    ambigu. N'est appelee que lorsque detect_department() ne trouve rien."""
    if not query or not query.strip():
        return None

    matrice, depts = _prototypes_departement(model)

    q_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(q_vec)

    sims = matrice @ q_vec[0]

    # Meilleure similarite par departement.
    par_dept: dict = {}
    for dept, s in zip(depts, sims):
        par_dept[dept] = max(par_dept.get(dept, -1.0), float(s))

    classement = sorted(par_dept.items(), key=lambda x: x[1], reverse=True)
    meilleur_dept, meilleur_score = classement[0]
    second_score = classement[1][1] if len(classement) > 1 else -1.0

    _dbg(
        "Embeddings departement : "
        + ", ".join(f"{d}={s:.2f}" for d, s in classement[:3])
    )

    if meilleur_score < SEUIL_EMBEDDING_DEPARTEMENT:
        return None

    if meilleur_score - second_score < MARGE_EMBEDDING_DEPARTEMENT:
        # Ambigu : le departement du role departage s'il est dans la marge.
        proches = [
            d for d, s in classement
            if meilleur_score - s < MARGE_EMBEDDING_DEPARTEMENT
        ]
        if user_role in proches:
            return user_role
        return None

    return meilleur_dept


# ============================================================================
# Messages
# ============================================================================

MESSAGE_ABSENTE = (
    "Je ne dispose pas actuellement d'informations suffisantes dans les "
    "documents disponibles pour répondre précisément à cette question.\n\n"
    "Afin de garantir une réponse fiable, je préfère ne pas fournir "
    "d'information qui ne pourrait pas être vérifiée."
)

MESSAGE_DEPARTEMENT_VIDE = (
    "Aucun document n'est actuellement indexé pour le département "
    "{dept}.\n\n"
    "Je ne peux donc pas répondre à cette question sans risque "
    "d'inexactitude. Veuillez contacter l'administrateur afin de vérifier "
    "que les documents de ce département ont bien été ingérés."
)

MESSAGE_CLARIFICATION_PERIMETRE = (
    "Précision nécessaire\n\n"
    "Les documents disponibles contiennent à la fois des valeurs sociales "
    "et des valeurs consolidées pour cet indicateur, et ces valeurs sont "
    "différentes.\n\n"
    "Souhaitez-vous le périmètre social ou le périmètre consolidé ? "
    "Reformulez votre question en le précisant."
)

MESSAGE_QUOTA = (
    "Service momentanément saturé\n\n"
    "Le service de génération a atteint sa limite d'utilisation. "
    "Cela ne signifie pas que l'information est absente des documents. "
    "Veuillez réessayer dans quelques minutes."
)


def message_refus_acces(
    user_role: str,
    departement: str | None = None,
    entreprises: set | None = None,
) -> str:
    """Message professionnel de refus d'acces, adapte a la situation :
    documents d'une entreprise nommee (prioritaire), departement detecte,
    ou perimetre restreint non precise."""
    profil = LIBELLE_DEPARTEMENT.get(user_role)
    profil_txt = f"votre profil actuel ({profil})" if profil else "votre profil actuel"

    if entreprises:
        noms = ", ".join(sorted(e.replace("_", " ") for e in entreprises))
        objet = f"concerne des documents à accès restreint ({noms})"
    elif departement in LIBELLE_DEPARTEMENT:
        objet = f"relève du département {LIBELLE_DEPARTEMENT[departement]}"
    else:
        objet = "relève d'un périmètre à accès restreint"

    return (
        "Accès non autorisé\n\n"
        f"Votre demande {objet}. Compte tenu de {profil_txt}, vous ne "
        "disposez pas des autorisations nécessaires pour consulter ces "
        "informations.\n\n"
        "Si cet accès est nécessaire à votre activité, nous vous invitons "
        "à adresser votre demande au responsable du département concerné "
        "ou à l'administrateur de la plateforme, qui pourra examiner "
        "l'ajustement de vos droits.\n\n"
        "Je reste à votre disposition pour toute question relevant de "
        "votre périmètre."
    )


# ============================================================================
# Detection d'entreprise et recherche
# ============================================================================

def detect_entreprises(query: str, noms_connus: set) -> set:
    """Entreprises explicitement nommees dans la question (frontieres de
    mots)."""
    q = query.lower()
    trouvees = set()

    for nom in noms_connus:
        variantes = {
            nom.lower(),
            nom.lower().replace("_", " "),
            nom.lower().replace("_", "-"),
        }
        if any(re.search(rf"\b{re.escape(v)}\b", q) for v in variantes):
            trouvees.add(nom)

    for alias, canonique in ALIAS_ENTREPRISES.items():
        if re.search(rf"\b{re.escape(alias)}\b", q) and canonique in noms_connus:
            trouvees.add(canonique)

    return trouvees


def score_lexical(
    query_words: list,
    annees: list,
    famille: str | None,
    content: str,
    numero_article: str | None = None,
    secteur=None,
) -> float:
    """Score lexical dans [0, 1]."""
    if not query_words and not numero_article:
        return 0.0

    content_lower = content.lower()

    matches = sum(
        1 for w in query_words if re.search(rf"\b{re.escape(w)}\b", content_lower)
    )
    ratio = matches / len(query_words) if query_words else 0.0

    bonus_annee = (
        1.0
        if any(re.search(rf"\b{re.escape(a)}\b", content) for a in annees)
        else 0.0
    )

    if terme_generique_present(famille, content):
        bonus_phrase = 1.0
    elif terme_sectoriel_present(famille, secteur, content):
        bonus_phrase = 0.6
    else:
        bonus_phrase = 0.0

    bonus_article = 0.0

    if numero_article:
        if est_titre_article(content, numero_article):
            bonus_article = 1.0
        elif est_renvoi_article(content, numero_article):
            bonus_article = 0.25

    return min(
        1.0,
        ratio * 0.40
        + bonus_annee * 0.05
        + bonus_phrase * 0.35
        + bonus_article * 0.20,
    )


def search(
    query: str,
    model,
    index,
    metadata,
    user_role: str,
    top_k: int = TOP_K_RETRIEVAL,
    selected_department: str | None = None,
):
    """Recherche hybride FAISS + lexical, avec rescue metier.

    Ordre des filtres : controle d'acces (est_accessible) PUIS perimetre
    (departement, entreprise nommee). Le departement est un filtre de
    perimetre ; la securite reste portee par est_accessible().
    """
    query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_vec)

    scores, indices = index.search(query_vec, index.ntotal)

    faiss_par_idx = {
        int(idx): float(score)
        for score, idx in zip(scores[0], indices[0])
        if idx != -1
    }

    query_words = mots_utiles(query)
    annees = re.findall(r"\b(?:19|20)\d{2}\b", query)
    famille = detect_famille(query)
    metric_demande = detect_metric(query)
    numero_article = detect_reference_article(query)
    requested_year, temporal_mode = detect_temporal_requirement(query)

    noms_connus = {c.get("entreprise") for c in metadata if c.get("entreprise")}
    entreprises_visees = detect_entreprises(query, noms_connus)

    resultats = []
    vus = set()
    pool_metrique, pool_generique, pool_sectoriel, pool_temporel = [], [], [], []

    for idx, chunk in enumerate(metadata):

        if not est_accessible(chunk, user_role):
            continue

        type_document = chunk.get("type_document", "entreprise")
        est_reglementaire = type_document == "public_reglementaire"

        if (
            selected_department
            and not est_reglementaire
            and not chunk_matches_department(chunk, selected_department)
        ):
            continue

        if (
            entreprises_visees
            and not est_reglementaire
            and chunk.get("entreprise") not in entreprises_visees
        ):
            continue

        content = chunk.get("content", "")

        if not content:
            continue

        cle = (chunk.get("fichier_source"), chunk.get("page"), content[:120])

        if cle in vus:
            continue

        vus.add(cle)

        s_faiss = faiss_par_idx.get(idx, 0.0)

        s_lex = score_lexical(
            query_words, annees, famille, content,
            numero_article=numero_article, secteur=chunk.get("secteur"),
        )

        hybride = POIDS_FAISS * s_faiss + POIDS_LEXICAL * s_lex

        article_titre = (
            est_titre_article(content, numero_article) if numero_article else False
        )

        est_generique = terme_generique_present(famille, content)
        est_sectoriel = (
            not est_generique
            and terme_sectoriel_present(famille, chunk.get("secteur"), content)
        )
        a_terme_metier = est_generique or est_sectoriel

        if hybride < 0.20 and not article_titre and not a_terme_metier:
            continue

        if s_lex > s_faiss + 0.15:
            origine = "lexical"
        elif s_faiss > s_lex + 0.15:
            origine = "faiss"
        else:
            origine = "hybride"

        temporal_status = classify_chunk_temporal(chunk, requested_year)

        resultat = {
            "score": hybride,
            "entreprise": chunk.get("entreprise"),
            "secteur": chunk.get("secteur"),
            "page": chunk.get("page"),
            "fichier_source": chunk.get("fichier_source"),
            "content": content,
            "is_synthetic": chunk.get("is_synthetic", False),
            "type_document": type_document,
            "departement": chunk.get("departement"),
            "departements": chunk.get("departements"),
            "_source": origine,
            "_faiss_score": s_faiss,
            "_lexical_score": s_lex,
            "_article_titre": article_titre,
            "_terme_metier": a_terme_metier,
            "_terme_generique": est_generique,
            "_terme_sectoriel": est_sectoriel,
            "_scope": detect_chunk_scope(content),
            "_temporal_status": temporal_status,
        }

        resultats.append(resultat)

        if requested_year is not None and (
            (temporal_mode == "actual" and temporal_status == "actual")
            or (temporal_mode == "planned"
                and temporal_status in {"actual", "planned"})
        ):
            pool_temporel.append(resultat)

        # Pools de rescue : chunks d'entreprise uniquement (un texte de loi
        # qui cite incidemment "chiffre d'affaires" ne repond jamais a une
        # question sur une entreprise et evincerait la vraie donnee).
        if not est_reglementaire:

            if metric_demande and _preuve_metric_locale(content, metric_demande):
                pool_metrique.append(resultat)

            if est_generique:
                pool_generique.append(resultat)
            elif est_sectoriel:
                pool_sectoriel.append(resultat)

    resultats.sort(key=lambda r: r["score"], reverse=True)

    limite = top_k + 10
    top_resultats = resultats[:limite]
    max_rescue = 10

    pools = []

    if pool_temporel:
        pools.append(("temporel", pool_temporel))
    if metric_demande:
        # Priorite a la metrique LITTERALE, avant les pools de famille.
        pools.append(("metrique", pool_metrique))
    pools.append(("generique", pool_generique))
    pools.append(("sectoriel", pool_sectoriel))

    if any(pool for _, pool in pools):

        cles_top = {
            (r["fichier_source"], r["page"], r["content"][:120])
            for r in top_resultats
        }
        injectes = 0

        for niveau, pool in pools:

            if injectes >= max_rescue:
                break

            hors_top = sorted(
                (
                    r for r in pool
                    if (r["fichier_source"], r["page"], r["content"][:120])
                    not in cles_top
                ),
                key=lambda r: r["score"],
                reverse=True,
            )

            for r in hors_top:

                if injectes >= max_rescue:
                    break

                if len(top_resultats) >= limite:
                    # Ne jamais ejecter un chunk qui porte la preuve de la
                    # metrique demandee.
                    for i in range(len(top_resultats) - 1, -1, -1):
                        if not (
                            metric_demande
                            and _preuve_metric_locale(
                                top_resultats[i].get("content", ""),
                                metric_demande,
                            )
                        ):
                            top_resultats.pop(i)
                            break

                top_resultats.append(r)
                cles_top.add((r["fichier_source"], r["page"], r["content"][:120]))
                injectes += 1

                _dbg(
                    f"Rescue ({niveau}) : {r.get('fichier_source')} "
                    f"p.{r.get('page')} score={r.get('score', 0):.3f}"
                )

    return top_resultats


def search_without_rbac(query: str, model, index, metadata, top_k: int = 10):
    """Recherche FAISS sans filtre RBAC, uniquement pour distinguer
    "information absente" de "information existante mais non autorisee"
    (voir check_rbac_restriction)."""
    query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_vec)

    scores, indices = index.search(query_vec, index.ntotal)

    noms_connus = {c.get("entreprise") for c in metadata if c.get("entreprise")}
    entreprises_visees = detect_entreprises(query, noms_connus)

    resultats = []

    for score, idx in zip(scores[0], indices[0]):

        if idx == -1:
            continue

        chunk = metadata[idx]

        if entreprises_visees and chunk.get("entreprise") not in entreprises_visees:
            continue

        resultats.append({
            "score": float(score),
            "entreprise": chunk.get("entreprise"),
            "secteur": chunk.get("secteur"),
            "page": chunk.get("page"),
            "fichier_source": chunk.get("fichier_source"),
            "allowed_roles": sorted(effective_allowed_roles(chunk)),
            # Champs lus par effective_allowed_roles() : sans eux, le calcul
            # retomberait sur RBAC_POLICY seule (faux HORS_PERIMETRE).
            "access_roles": chunk.get("access_roles"),
            "departement": chunk.get("departement"),
            "type_document": chunk.get("type_document", "entreprise"),
        })

        if len(resultats) >= top_k:
            break

    return resultats


def check_rbac_restriction(
    query: str, model, index, metadata, user_role: str, authorized_results: list
) -> bool:
    """Vrai si des documents pertinents existent mais ne sont pas
    autorises pour ce role."""
    public_threshold = 0.55

    if authorized_results:

        if authorized_results[0].get("_faiss_score", 0.0) >= 0.72:
            return False

        for r in authorized_results:
            if (
                r.get("type_document") == "public_reglementaire"
                and r.get("score", 0) >= public_threshold
            ):
                return False

    tous = search_without_rbac(query, model, index, metadata, top_k=10)

    if not tous:
        return False

    # Pages (fichier, page) que ce role peut lire par au moins un chunk : un
    # doublon interdit de la meme page (ex : meme texte ingere dans deux
    # departements) ne constitue pas une restriction reelle.
    pages_accessibles = {
        (c.get("fichier_source"), c.get("page"))
        for c in metadata
        if est_accessible(c, user_role)
    }

    interdits = [
        r for r in tous
        if r["score"] >= 0.5
        and user_role not in effective_allowed_roles(r)
        and (r.get("fichier_source"), r.get("page")) not in pages_accessibles
    ]

    if interdits:
        _dbg(
            f"RBAC : {len(interdits)} chunk(s) pertinent(s) interdit(s) pour "
            f"{user_role!r} : "
            + "; ".join(
                f"{r.get('fichier_source')} p.{r.get('page')} "
                f"dept={r.get('departement')!r} score={r['score']:.2f}"
                for r in interdits[:5]
            )
        )

    if len(interdits) >= 2:
        return True

    if len(interdits) == 1 and interdits[0]["score"] >= 0.6:
        meilleur_autorise = (
            authorized_results[0].get("_faiss_score", 0.0)
            if authorized_results else 0.0
        )
        return interdits[0]["score"] > meilleur_autorise + 0.1

    return False


# ============================================================================
# Reclassement des candidats
# ============================================================================

_RE_CA_SOUS_PERIMETRE = re.compile(
    r"""
    \bchiffre\s+d['’]?\s*affaires\s+
        (?: de\s+la\s+filiale
          | des?\s+filiales
          | de\s+l['’]?\s*activit[ée]s?
          | (?:TPME|TPE|PME)
          | (?:RDS|risques?\s+divers)
          | par\s+(?:activit[ée]|branche|segment|m[ée]tier) )
    | \b(?:TPME|TPE|PME|RDS)\b .*? \bchiffre\s+d['’]?\s*affaires
    | \brisques?\s+divers\b .*? \bchiffre\s+d['’]?\s*affaires
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)

_RE_VALEUR_PROCHE = re.compile(
    r"\d[\d\s.,]*\s*(?:mmdh|mdh|mmad|kmad|mad|dh|dirhams?|millions?|milliards?)",
    flags=re.IGNORECASE,
)


def select_best_candidates(
    query: str, results: list, top_n: int = TOP_K_VERIFY
) -> list:
    """Reclasse les resultats (score de reclassement stocke dans
    r["_score_reclasse"], r["score"] reste le score de retrieval brut) et
    selectionne les top_n candidats a verifier."""
    if not results:
        return []

    famille = detect_famille(query)
    scope_demande = detect_scope(query)
    metric_demande = detect_metric(query)
    demande_filiale = bool(_RE_FILIALES.search(_norm(query)))
    requested_year, temporal_mode = detect_temporal_requirement(query)

    scored = []

    for r in results:
        content = r.get("content", "")
        content_norm = _norm(content)
        bonus = 0.0

        # 1. Titre d'article
        if r.get("_article_titre"):
            bonus += BONUS_ARTICLE_TITRE

        # 2-3. Terme metier generique / sectoriel
        termes_niveau = termes_generiques_famille(famille)
        est_generique = contient_un_des_termes(content, termes_niveau)
        est_sectoriel = False

        if not est_generique:
            termes_niveau = termes_sectoriels_famille(famille, r.get("secteur"))
            est_sectoriel = contient_un_des_termes(content, termes_niveau)

        if est_generique:
            bonus += 0.45
        elif est_sectoriel:
            bonus += 0.20

        # 4. Terme metier proche d'une valeur
        if est_generique or est_sectoriel:
            for t in termes_niveau:
                m = position_terme(content, t)
                if m is None:
                    continue
                fenetre = content[max(0, m.start() - 250):m.start() + 500]
                if _RE_VALEUR_PROCHE.search(fenetre):
                    bonus += 0.20
                    break

        # 5. Perimetre comptable
        scope_chunk = detect_chunk_scope(content)
        r["_scope"] = scope_chunk

        if scope_demande and scope_chunk:
            bonus += 0.30 if scope_chunk == scope_demande else -0.35

        # 6. Filiales / devises etrangeres
        if not demande_filiale and scope_chunk != "consolide":
            if _RE_FILIALES.search(content_norm):
                bonus -= 0.30
            if _RE_DEVISES.search(content_norm):
                bonus -= 0.25

        # 7. Metrique litterale
        r["_preuve_metric"] = False
        r["_ca_sous_perimetre"] = False

        if metric_demande:
            preuve = _preuve_metric_locale(content, metric_demande)
            r["_preuve_metric"] = preuve

            if preuve:
                bonus += 0.40
            elif metric_demande in metriques_presentes(content):
                bonus -= 0.10
            else:
                bonus -= 0.45

            if metric_demande == "chiffre_affaires":
                if _RE_CA_SOUS_PERIMETRE.search(content):
                    r["_ca_sous_perimetre"] = True
                    bonus -= 0.65
                else:
                    bonus += 0.20

        # 8. Temporalite
        temporal_status = (
            classify_chunk_temporal(r, requested_year) if requested_year else "unknown"
        )
        r["_temporal_status"] = temporal_status

        if requested_year:
            if temporal_mode == "actual":
                bonus += {"actual": 0.55, "planned": -0.65}.get(temporal_status, -0.20)
            elif temporal_mode == "planned":
                bonus += {"planned": 0.40, "actual": 0.15}.get(temporal_status, 0.0)

        score_final = r.get("score", 0.0) + bonus
        r["_score_reclasse"] = score_final
        scored.append((score_final, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    if DEBUG:
        for rang, (s, r) in enumerate(scored[:10], start=1):
            print(
                f"[DEBUG] reclassement #{rang} : {s:.3f} "
                f"(retrieval={r.get('score', 0):.3f}) p.{r.get('page')} "
                f"scope={r.get('_scope')} preuve_metric={r.get('_preuve_metric')} "
                f"ca_sous_perimetre={r.get('_ca_sous_perimetre')}"
            )

    # Selection : preuve de la metrique d'abord, puis meilleurs scores,
    # puis filet de securite sans limite par page. Un CA de sous-perimetre
    # n'est JAMAIS selectionne.
    max_per_page = 2
    selected, deja, page_counts = [], set(), Counter()

    def ajouter(r, limite_page=True):
        if metric_demande == "chiffre_affaires" and r.get("_ca_sous_perimetre"):
            return

        cle = (r["fichier_source"], r["page"], r["content"][:100])
        cle_page = (r["fichier_source"], r["page"])

        if cle in deja:
            return
        if limite_page and page_counts[cle_page] >= max_per_page:
            return

        selected.append(r)
        deja.add(cle)
        page_counts[cle_page] += 1

    if metric_demande:
        for _, r in scored:
            if len(selected) >= top_n:
                break
            if r.get("_preuve_metric"):
                ajouter(r)

    for _, r in scored:
        if len(selected) >= top_n:
            break
        ajouter(r)

    for _, r in scored:
        if len(selected) >= top_n:
            break
        ajouter(r, limite_page=False)

    return selected


# ============================================================================
# Verification de pertinence
# ============================================================================

def parse_json_response(content: str) -> dict:
    content = content.strip()

    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0].strip()

    start, end = content.find("{"), content.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("Aucun objet JSON trouve dans la reponse")

    return json.loads(content[start:end + 1])


def local_relevance_fallback(query: str, contexts: list) -> tuple:
    """Verification locale lorsque l'appel Groq echoue. Retourne
    (can_answer, confidence)."""
    if not contexts:
        return False, 0.0

    top_contexts = contexts[:TOP_K_VERIFY]
    annees_demandees = set(re.findall(r"\b(?:19|20)\d{2}\b", query))

    if annees_demandees:
        requested_year, temporal_mode = detect_temporal_requirement(query)

        if requested_year and temporal_mode == "actual":
            if not any(
                classify_chunk_temporal(c, requested_year) == "actual"
                for c in top_contexts
            ):
                _dbg(f"Fallback local : aucune preuve reelle pour {requested_year}.")
                return False, 0.0

        # L'annee est cherchee dans le contenu ET le nom du fichier.
        annees_docs = set()
        for ctx in top_contexts:
            texte = ctx.get("content", "") + " " + ctx.get("fichier_source", "")
            annees_docs.update(re.findall(r"\b(?:19|20)\d{2}\b", texte))

        if annees_demandees - annees_docs:
            _dbg("Fallback local : annee demandee absente des extraits.")
            return False, 0.0

    numero_article = detect_reference_article(query)

    if numero_article and not any(
        est_titre_article(c.get("content", ""), numero_article)
        for c in top_contexts
    ):
        _dbg(f"Fallback local : aucun extrait ne porte l'article {numero_article}.")
        return False, 0.0

    query_words = mots_utiles(query, longueur_min=4)

    if not query_words:
        return False, 0.0

    texte = " ".join(c.get("content", "").lower() for c in top_contexts)
    matches = sum(1 for w in query_words if re.search(rf"\b{re.escape(w)}\b", texte))
    match_ratio = matches / len(query_words)
    best_score = max(c.get("score", 0.0) for c in top_contexts)

    sources = [c.get("fichier_source") for c in top_contexts if c.get("fichier_source")]

    if not sources:
        return False, 0.0

    occurrences = sources.count(max(set(sources), key=sources.count))
    a_reglementaire = any(
        c.get("type_document") == "public_reglementaire" for c in top_contexts
    )

    if a_reglementaire and best_score >= 0.55 and occurrences >= 3 and match_ratio >= 0.35:
        return True, 0.75

    if best_score < 0.55 or occurrences < 3:
        return False, 0.0

    return (True, 0.70) if match_ratio >= 0.35 else (False, 0.0)


_REGLES_METRIC = {
    "chiffre_affaires": (
        "12. METRIQUE OBLIGATOIRE : la question demande le chiffre d'affaires. "
        "Un extrait qui contient uniquement des primes émises, primes acquises, "
        "revenus d'assurance ou produits des activités d'assurance ne constitue "
        "PAS une preuve du chiffre d'affaires, même si le périmètre, l'année et "
        "l'entreprise correspondent. Ne les transforme jamais en \"chiffre "
        "d'affaires\".\n"
    ),
    "primes_emises": (
        "12. METRIQUE OBLIGATOIRE : la question demande les primes émises. Un "
        "chiffre d'affaires, un résultat net ou des revenus d'assurance ne "
        "constituent PAS automatiquement une preuve des primes émises.\n"
    ),
    "revenus_assurance": (
        "12. METRIQUE OBLIGATOIRE : la question demande les revenus "
        "d'assurance. Les primes émises ou le chiffre d'affaires ne doivent "
        "pas être présentés comme tels sans preuve explicite.\n"
    ),
    "produits_activites_assurance": (
        "12. METRIQUE OBLIGATOIRE : la question demande les produits des "
        "activités d'assurance. Un chiffre d'affaires, des primes émises ou un "
        "résultat net ne doivent pas être présentés comme tels sans preuve "
        "explicite.\n"
    ),
    "resultat_net": (
        "12. METRIQUE OBLIGATOIRE : la question demande le résultat net. Un "
        "chiffre d'affaires, des primes émises ou des revenus d'assurance ne "
        "constituent PAS une preuve du résultat net.\n"
    ),
}


def _regles_verification(query: str, contexts: list) -> str:
    """Regles supplementaires du verificateur (article, secteur, perimetre,
    metrique, temporalite), en defense en profondeur des filtres Python."""
    regles = ""

    numero = detect_reference_article(query)

    if numero:
        regles += (
            f"8. La question porte sur l'article {numero}. Reponds true "
            "UNIQUEMENT si l'un des extraits contient le TEXTE de cet "
            "article. Une simple mention du type \"conformement a l'article "
            f"{numero}\" est un renvoi : dans ce cas, reponds false.\n"
        )

    if detect_famille(query) == "chiffre_affaires" and any(
        secteur_est_assurance(r.get("secteur")) for r in contexts[:TOP_K_VERIFY]
    ):
        regles += (
            "9. Si un extrait emploie LITTERALEMENT l'expression \"chiffre "
            "d'affaires\", il constitue la reponse prioritaire : reponds true "
            "et designe-le dans \"extraits\" de preference a tout autre.\n"
            "10. Ne considere PAS par defaut les primes émises/acquises, les "
            "produits des activités d'assurance ou les revenus d'assurance "
            "comme equivalents au chiffre d'affaires. N'accepte un indicateur "
            "sectoriel que si AUCUN extrait ne contient le terme litteral "
            "\"chiffre d'affaires\", et nomme-le alors comme tel.\n"
        )

    scope = detect_scope(query)

    if scope == "consolide":
        regles += (
            "11. PERIMETRE CONSOLIDE OBLIGATOIRE : un extrait \"résultats "
            "sociaux\" ou \"comptes sociaux\" ne peut PAS servir de preuve, "
            "même avec le même indicateur et la bonne année. Reponds false si "
            "aucun extrait ne fournit une valeur explicitement consolidée. Ne "
            "transforme jamais un chiffre social en chiffre consolidé.\n"
        )
    elif scope == "social":
        regles += (
            "11. PERIMETRE SOCIAL OBLIGATOIRE : un chiffre provenant "
            "uniquement de comptes consolidés ne peut pas servir de preuve. "
            "Reponds false si aucun extrait ne fournit le chiffre social "
            "demandé.\n"
        )

    regles += _REGLES_METRIC.get(detect_metric(query), "")

    year, mode = detect_temporal_requirement(query)

    if year and mode == "actual":
        regles += (
            f"13. TEMPORALITE OBLIGATOIRE : la question demande des "
            f"informations réalisées en {year}. Un passage disant seulement "
            f"qu'une action est prévue ou constitue un objectif pour {year} "
            "ne prouve PAS un résultat réalisé. Si seuls des éléments "
            "prospectifs sont fournis, reponds false.\n"
        )
    elif year and mode == "planned":
        regles += (
            f"13. TEMPORALITE : la question porte sur les plans/prévisions "
            f"pour {year}. Les passages prospectifs sont admissibles, mais ne "
            "les présente jamais comme des résultats déjà réalisés.\n"
        )

    return regles


def verify_relevance(query: str, contexts: list) -> tuple:
    """Retourne (can_answer, confidence, verify_error, extraits)."""
    if not contexts:
        return False, 0.0, False, []

    context_preview = "\n\n".join(
        f"[Extrait {i + 1} - {r['entreprise']} - page {r['page']}]\n"
        f"{r['content'][:VERIFY_CHARS]}"
        for i, r in enumerate(contexts[:TOP_K_VERIFY])
    )

    verification_prompt = (
        "Tu es un verificateur de pertinence pour un assistant RAG.\n\n"
        f"QUESTION UTILISATEUR :\n{query}\n\n"
        f"EXTRAITS DE DOCUMENTS :\n{context_preview}\n\n"
        "Determine si les extraits contiennent suffisamment d'informations "
        "factuelles pour repondre a la question.\n\n"
        "REGLES :\n"
        "1. Reponds true si les extraits permettent de construire une "
        "reponse factuelle a la question.\n"
        "2. Les informations peuvent etre reparties entre plusieurs "
        "extraits.\n"
        "3. Une reformulation ou un synonyme de la question est acceptable.\n"
        "4. Reponds false si les informations necessaires ne sont pas "
        "presentes.\n"
        "5. Reponds false si les seuls chiffres disponibles concernent une "
        "autre entite, un autre perimetre ou une autre devise que ce qui est "
        "demande.\n"
        "6. N'utilise aucune connaissance externe.\n"
        "7. Indique dans \"extraits\" les numeros des extraits qui portent "
        "reellement la reponse.\n"
        f"{_regles_verification(query, contexts)}"
        "\nReponds UNIQUEMENT avec un JSON valide, sans texte avant ou apres, "
        "sans backticks :\n"
        '{\n  "can_answer": true,\n  "confidence": 0.95,\n  "extraits": [1, 5]\n}'
    )

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_VERIFY_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un verificateur strict de pertinence RAG. "
                        "Reponds avec EXACTEMENT un objet JSON valide "
                        "contenant \"can_answer\" (boolean), \"confidence\" "
                        "(nombre entre 0 et 1) et \"extraits\" (liste "
                        "d'entiers). Exemple : {\"can_answer\": true, "
                        "\"confidence\": 0.95, \"extraits\": [1]}"
                    ),
                },
                {"role": "user", "content": verification_prompt},
            ],
            temperature=0.0,
            max_tokens=1200,
        )

        response_text = response.choices[0].message.content or ""
        _dbg(f"Verifier content : {response_text!r}")

        try:
            result = parse_json_response(response_text.strip())
        except Exception as parse_error:
            _dbg(f"Echec parsing du verifier : {parse_error}")
            can_answer, confidence = local_relevance_fallback(query, contexts)
            return can_answer, confidence, True, []

        can_answer = bool(result.get("can_answer", False))
        confidence = float(result.get("confidence", 0.0))
        extraits = result.get("extraits") or []

        valides = [
            n for n in extraits
            if isinstance(n, int) and 1 <= n <= len(contexts[:TOP_K_VERIFY])
        ]

        if can_answer and extraits and not valides:
            _dbg(f"Extraits cites invalides : {extraits}")
            confidence = min(confidence, 0.4)

        numero = detect_reference_article(query)

        if can_answer and numero:
            cibles = (
                [contexts[n - 1] for n in valides]
                if valides else contexts[:TOP_K_VERIFY]
            )
            if not any(est_titre_article(c.get("content", ""), numero) for c in cibles):
                _dbg(f"Aucun extrait ne porte le texte de l'article {numero}.")
                return False, 0.0, False, valides

        return can_answer, confidence, False, valides

    except RateLimitError as e:
        raise QuotaError(str(e)) from e

    except Exception as e:
        print(f"  [Debug] Erreur verification : {e}")
        can_answer, confidence = local_relevance_fallback(query, contexts)
        return can_answer, confidence, True, []


# ============================================================================
# Classification d'intention
# ============================================================================

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


# ============================================================================
# Citations
# ============================================================================

RE_BLOC_CROCHETS = re.compile(r"[\[【]([^\]】]{0,200})[\]】]")

RE_NUMEROS_SOURCE = re.compile(
    r"sources?\s*n?[°o]?\s*(\d+(?:\s*(?:,|;|et|&|/)\s*\d+)*)",
    flags=re.IGNORECASE,
)


def extract_cited_sources(answer: str, results: list) -> list:
    """Sources explicitement citees ("[Source 1 - fichier, page 125]",
    "[Sources 2 et 3]"...)."""
    cited = set()

    for bloc in RE_BLOC_CROCHETS.findall(answer):
        for m in RE_NUMEROS_SOURCE.finditer(bloc):
            cited.update(int(n) for n in re.findall(r"\d+", m.group(1)))

    return [(i, r) for i, r in enumerate(results, start=1) if i in cited]


def _remap_source_numbers(text: str, mapping: dict) -> str:
    """Reecrit les numeros LOCAUX des blocs [Source N] en numeros GLOBAUX."""

    def _bloc(m):
        bloc = m.group(0)
        nouveau = re.sub(
            r"\d+", lambda nm: str(mapping.get(int(nm.group(0)), nm.group(0))),
            m.group(1),
        )
        return bloc[0] + nouveau + bloc[-1]

    return RE_BLOC_CROCHETS.sub(_bloc, text)


def renumber_multi_intent_sources(sous_reponses: list) -> list:
    """Numerotation globale unique des sources citees par plusieurs
    sous-reponses ; met a jour le texte de chaque sous-reponse."""
    combined, compteur = [], 1

    for sr in sous_reponses:
        res = sr["result"]
        local_cited = res.get("cited_sources", [])

        if not local_cited:
            continue

        mapping = {}

        for local_i, r in local_cited:
            mapping[local_i] = compteur
            combined.append((compteur, r))
            compteur += 1

        res["answer"] = _remap_source_numbers(res.get("answer", ""), mapping)

    return combined


# ============================================================================
# Generation
# ============================================================================

def _contexte_departement(departement: str | None) -> str:
    if departement not in LIBELLE_DEPARTEMENT:
        return ""
    return (
        f"La question relève du département {LIBELLE_DEPARTEMENT[departement]} : "
        "adapte le vocabulaire et mets en avant les éléments les plus utiles "
        "à ce métier.\n"
    )


_FORMAT_TEXTE_PROPRE = (
    "FORMAT OBLIGATOIRE : texte brut professionnel. N'utilise AUCUN markdown : "
    "pas de '#', pas de '**', pas de '__', pas de tableau, pas de balise HTML. "
    "Un titre est une ligne simple terminée par ':' ; une liste utilise des "
    "lignes commençant par '- '. Phrases courtes et claires.\n"
)


def _chat(messages: list, temperature: float, max_tokens: int):
    """Appel Groq. Le modele (gpt-oss) consomme des tokens de raisonnement
    sur le budget max_tokens : on limite l'effort de reflexion pour eviter
    les reponses vides ou tronquees. Si le SDK ou le modele refuse
    "reasoning_effort", on retente sans ce parametre."""
    try:
        return groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort="low",
        )
    except RateLimitError as e:
        raise QuotaError(str(e)) from e
    except Exception as e:
        _dbg(f"reasoning_effort refuse ({e}) : nouvel essai sans ce parametre.")
        return groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def _nom_source(r: dict) -> str:
    """Nom lisible d'une source : entreprise, ou "Texte reglementaire"."""
    if r.get("entreprise"):
        return str(r["entreprise"])
    if r.get("type_document") == "public_reglementaire":
        return "Texte réglementaire"
    return "Document interne"


def generate_general_answer(query: str, departement: str | None = None) -> str:
    """Reponse generale (sans RAG), en texte propre."""
    system_prompt = (
        "Tu es un assistant professionnel au sein d'une entreprise.\n"
        "La question est d'ordre général et ne concerne PAS les données "
        "internes de l'entreprise : réponds avec tes connaissances générales, "
        "de façon précise, concise et professionnelle, en français.\n"
        "N'invente jamais de données propres à une entreprise.\n"
        "Le contexte est le Maroc : ne cite jamais le droit ou la "
        "réglementation d'un autre pays sauf si la question le demande.\n"
        f"{_contexte_departement(departement)}"
        f"{_FORMAT_TEXTE_PROPRE}"
    )

    response = _chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.2,
        max_tokens=1500,
    )

    choix = response.choices[0]
    _dbg(f"Reponse generale : finish_reason={choix.finish_reason}")
    texte = nettoyer_reponse(choix.message.content)

    return texte or (
        "Je n'ai pas pu formuler de réponse à cette question. "
        "Pouvez-vous la reformuler ?"
    )


def generate_answer(
    query: str,
    rag_results: list,
    user_role: str,
    departement: str | None = None,
) -> str:
    """Reponse ENTREPRISE (RAG) a partir des extraits DEJA valides par
    verify_relevance(), avec citations [Source N], en texte propre."""
    if not rag_results:
        return MESSAGE_ABSENTE

    contexte = "\n\n".join(
        f"[Source {i}] {_nom_source(r)} - {r.get('fichier_source')} - "
        f"page {r.get('page')}"
        + (
            " (DONNEE DE DEMONSTRATION SYNTHETIQUE -- a signaler comme telle)"
            if r.get("is_synthetic") else ""
        )
        + f"\n{r.get('content', '')[:1500]}"
        for i, r in enumerate(rag_results, start=1)
    )

    system_prompt = (
        "Tu es un assistant d'entreprise qui répond STRICTEMENT à partir des "
        "extraits de documents fournis ci-dessous. Tu n'utilises AUCUNE "
        "connaissance externe et n'inventes JAMAIS de chiffre, de nom ou de "
        "fait absent des extraits.\n\n"
        "REGLES OBLIGATOIRES :\n"
        "1. Chaque affirmation factuelle est suivie d'une citation au format "
        "[Source N], N étant le numéro de l'extrait ci-dessous "
        "(ex: [Source 1]). Plusieurs sources : [Source 1, Source 2].\n"
        "2. N'utilise QUE des crochets ASCII [ ] pour les citations, jamais "
        "de crochets pleine largeur.\n"
        "3. Si un extrait est marqué DONNEE DE DEMONSTRATION SYNTHETIQUE, "
        "signale-le et ne le présente jamais comme une donnée officielle.\n"
        "4. Si les extraits emploient un indicateur sectoriel équivalent "
        "(ex: primes émises pour une compagnie d'assurance), explique cette "
        "équivalence clairement plutôt que de la passer sous silence.\n"
        "5. Si une partie de la question n'est pas couverte par les extraits, "
        "dis-le explicitement au lieu de deviner.\n"
        "6. Réponds en français, de façon concise et factuelle.\n"
        "7. Pour tout chiffre cité, indique le périmètre (social ou "
        "consolidé) et l'année lorsque l'extrait les précise.\n"
        f"{_contexte_departement(departement)}"
        f"{_FORMAT_TEXTE_PROPRE}\n"
        f"Rôle de l'utilisateur : {user_role}\n\n"
        "EXTRAITS DE DOCUMENTS (déjà vérifiés comme pertinents) :\n"
        f"{contexte}"
    )

    response = _chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.0,
        max_tokens=3000,
    )

    choix = response.choices[0]
    _dbg(f"Reponse RAG : finish_reason={choix.finish_reason}")
    texte = nettoyer_reponse(choix.message.content)

    return texte or MESSAGE_ABSENTE


# ============================================================================
# Pipeline
# ============================================================================

def _resultat(answer: str, mode: str, type_: str, **extra) -> dict:
    """Dictionnaire de resultat avec toutes les cles par defaut."""
    base = {
        "answer": answer,
        "cited_sources": [],
        "all_results": [],
        "candidats_finaux": [],
        "max_score": 0.0,
        "mode": mode,
        "type": type_,
        "can_answer": False,
        "confidence": 0.0,
        "verify_error": False,
        "extraits_verifier": [],
        "incoherence_citation": False,
        "montant_structure": None,
        "departement": None,
    }
    base.update(extra)
    return base


def _pipeline_rag(
    query: str, model, index, metadata, user_role: str, departement: str | None,
    departement_contexte: str | None = None,
) -> dict:
    """Retrieval -> controle RBAC -> reclassement -> garde-fous Python ->
    verification LLM -> generation.

    `departement` sert de FILTRE de perimetre (peut etre None) ;
    `departement_contexte` est le departement detecte, utilise pour adapter
    le vocabulaire de la reponse meme quand aucun filtre n'est applique."""
    ctx_dept = departement_contexte or departement

    results = search(
        query, model, index, metadata, user_role=user_role,
        top_k=TOP_K_RETRIEVAL, selected_department=departement,
    )
    max_score = max((r.get("score", 0.0) for r in results), default=0.0)

    if check_rbac_restriction(query, model, index, metadata, user_role, results):
        noms = {c.get("entreprise") for c in metadata if c.get("entreprise")}
        return _resultat(
            message_refus_acces(
                user_role,
                departement=(
                    ctx_dept if department_access_denied(user_role, ctx_dept)
                    else None
                ),
                entreprises=detect_entreprises(query, noms),
            ),
            "HORS_PERIMETRE", "HORS_PERIMETRE",
            all_results=results, max_score=max_score,
        )

    candidats = select_best_candidates(query, results, top_n=TOP_K_VERIFY)
    avant_filtre = len(candidats)

    # Garde-fous deterministes AVANT le LLM : perimetre, metrique, temporalite.
    candidats = [
        r for r in candidats
        if not (
            scope_incompatible(query, r.get("content", ""))
            or metric_incompatible(query, r.get("content", ""))
            or temporal_incompatible(query, r)
        )
    ]

    _dbg(
        f"Garde-fous : {avant_filtre - len(candidats)} candidat(s) elimine(s) "
        f"(scope={detect_scope(query)!r}, metric={detect_metric(query)!r}, "
        f"temporalite={detect_temporal_requirement(query)!r})."
    )

    # Perimetre non precise alors que social ET consolide existent : on
    # demande lequel plutot que de choisir pour l'utilisateur.
    #
    # Le filtre par ANNEE est applique EN AMONT de ce bloc : `candidats` a
    # deja ete filtre par temporal_incompatible() (annee detectee par
    # detect_temporal_requirement(), qui reconnait 19xx et 20xx). Pour une
    # annee absente des documents (ex : 1999), `candidats` est donc vide et
    # aucune clarification n'est declenchee : la question aboutit a ABSENT.
    if candidats and detect_metric(query) and detect_scope(query) is None:
        perimetres = {
            detect_chunk_scope(r.get("content", "")) for r in candidats
        } - {None}

        if {"social", "consolide"} <= perimetres:
            return _resultat(
                MESSAGE_CLARIFICATION_PERIMETRE, "CLARIFICATION", "CLARIFICATION",
                all_results=results, candidats_finaux=candidats,
                max_score=max_score,
            )

    can_answer, confidence, verify_error, extraits = verify_relevance(query, candidats)

    # Sortie incoherente du verificateur (can_answer sans extrait designe) :
    # echec de verification. Exception : le fallback LOCAL (verify_error)
    # ne designe jamais d'extraits par construction.
    if can_answer and not extraits and not verify_error:
        _dbg("Verificateur incoherent : can_answer=True sans extrait designe.")
        can_answer = False
        confidence = min(confidence, 0.4)

    q_type = classify_question(query, results, can_answer, verify_error)

    rag_results = []
    cited_sources = []
    incoherence_citation = False
    montant_structure = None

    if q_type == "ENTREPRISE":

        if extraits:
            rag_results = [
                candidats[n - 1] for n in sorted(set(extraits))
                if 1 <= n <= len(candidats)
            ]
        else:
            rag_results = candidats[:TOP_K_CONTEXT]

        answer = generate_answer(query, rag_results, user_role, ctx_dept)
        cited_sources = extract_cited_sources(answer, rag_results)

        if rag_results and not cited_sources:
            incoherence_citation = True
            confidence = min(confidence, 0.6)

        mode = "RAG"

        if can_answer:
            metric = detect_metric(query)
            m = extraire_montant_source(rag_results, metric)

            if m:
                montant_structure = {
                    "valeur": m[0], "unite": m[1],
                    "scope": detect_scope(query), "metric": metric,
                }

    elif q_type == "ABSENTE":
        answer, mode = MESSAGE_ABSENTE, "ABSENT"

    else:
        answer = generate_general_answer(query, ctx_dept)
        mode = "GENERAL"

    return _resultat(
        answer, mode, q_type,
        cited_sources=cited_sources, all_results=results,
        candidats_finaux=rag_results, max_score=max_score,
        can_answer=can_answer, confidence=confidence,
        verify_error=verify_error, extraits_verifier=extraits,
        incoherence_citation=incoherence_citation,
        montant_structure=montant_structure,
    )


def process_comparative_question(
    query: str, model, index, metadata, user_role: str,
    selected_department: str | None = None,
) -> dict:
    """Question nommant 2+ indicateurs : une sous-question simple par
    indicateur, chacune passant par process_question_hybride() (donc par
    tous les garde-fous). Une difference n'est calculee que si les deux
    montants sont trouves dans LA MEME unite ; la reponse rappelle toujours
    que ce sont deux indicateurs distincts."""

    intents = detect_intents(query)

    if len(intents) < 2:
        return process_question_hybride(
            query, model, index, metadata, user_role,
            selected_department=selected_department,
        )

    noms_connus = {c.get("entreprise") for c in metadata if c.get("entreprise")}
    entreprises = detect_entreprises(query, noms_connus)
    entreprise_display = (
        sorted(entreprises)[0].replace("_", " ") if entreprises else ""
    )

    sous_reponses = []

    for intent in intents:
        subq = build_subquery(entreprise_display, intent)
        _dbg(f"Question comparative -> sous-question : {subq!r}")

        res = process_question_hybride(
            subq, model, index, metadata, user_role,
            selected_department=selected_department,
        )

        montant = None
        if res.get("type") == "ENTREPRISE" and res.get("can_answer"):
            m = res.get("montant_structure")
            if m:
                montant = (m["valeur"], m["unite"])

        sous_reponses.append(
            {"intent": intent, "subquery": subq, "result": res, "montant": montant}
        )

    cited_sources = renumber_multi_intent_sources(sous_reponses)

    lignes = []

    for sr in sous_reponses:
        intent, res = sr["intent"], sr["result"]
        label = _LIBELLE_METRIC.get(intent["metric"], intent["metric"])
        scope_txt = _LIBELLE_SCOPE.get(intent.get("scope")) or "périmètre non précisé"
        titre = f"{label.capitalize()} ({scope_txt}) :"

        if res.get("type") == "ENTREPRISE" and res.get("can_answer"):
            lignes.append(f"{titre}\n{res['answer']}")
        elif res.get("mode") == "CLARIFICATION":
            lignes.append(
                f"{titre}\nPérimètre à préciser : des valeurs sociales et "
                "consolidées existent pour cet indicateur (précisez « social » "
                "ou « consolidé »)."
            )
        elif res.get("mode") == "HORS_PERIMETRE":
            lignes.append(f"{titre}\n{res['answer']}")
        else:
            lignes.append(
                f"{titre}\nInformation absente ou non vérifiable dans les "
                "documents disponibles pour cet indicateur."
            )

    montants = [sr["montant"] for sr in sous_reponses if sr["montant"]]

    if len(montants) == len(sous_reponses) == 2:
        (v1, u1), (v2, u2) = montants

        if u1 == u2:
            scopes_differents = (
                sous_reponses[0]["intent"].get("scope")
                != sous_reponses[1]["intent"].get("scope")
            )
            diff_txt = (
                f"\n\nDifférence calculée : {abs(v1 - v2):g} {u1}.\n"
                "Attention : il ne s'agit pas d'une comparaison homogène, "
                "car ce sont deux indicateurs comptables distincts"
                + (", avec des périmètres potentiellement différents"
                   if scopes_differents else "")
                + ". Cette différence n'a de sens que si vous comparez "
                "explicitement ces deux notions précises."
            )
        else:
            diff_txt = (
                "\n\nLes deux montants trouvés sont exprimés dans des unités "
                f"différentes ({u1} et {u2}) : aucune différence n'est "
                "calculée afin d'éviter toute erreur d'unité."
            )
    else:
        diff_txt = (
            "\n\nUne différence n'a pas pu être calculée car au moins un des "
            "deux indicateurs n'a pas pu être extrait avec certitude des "
            "documents disponibles."
        )

    return _resultat(
        "\n\n".join(lignes) + diff_txt, "MULTI_INTENT", "MULTI_INTENT",
        cited_sources=cited_sources,
        max_score=max(
            (sr["result"].get("max_score", 0.0) for sr in sous_reponses),
            default=0.0,
        ),
        can_answer=all(sr["result"].get("can_answer") for sr in sous_reponses),
        confidence=min(
            (sr["result"].get("confidence", 0.0) for sr in sous_reponses),
            default=0.0,
        ),
        verify_error=any(sr["result"].get("verify_error") for sr in sous_reponses),
        sous_reponses=sous_reponses,
    )


def process_question_hybride(
    query: str,
    model,
    index,
    metadata,
    user_role: str,
    selected_department: str | None = None,
) -> dict:
    """Point d'entree du pipeline.

    Le departement est DETECTE automatiquement depuis la question
    (detect_department, mots-cles ; puis detect_department_embeddings en
    repli) ; `selected_department` reste accepte comme forcage explicite
    (compatibilite avec un appelant qui fournirait deja un onglet) et
    prime alors sur la detection.

    Etapes :
      1. departement = forcage explicite, sinon detection par mots-cles,
         sinon detection de repli par embeddings ;
      2. question generale -> reponse sans RAG (jamais refusee), sauf si
         un departement a ete detecte par mots-cles (ou force) : le RAG
         est alors tente, et le controle d'acces departement s'applique.
         Les questions de definition ("qu'est-ce que...") restent
         generales ;
      3. departement detecte par mots-cles non autorise pour ce role ->
         refus professionnel AVANT tout retrieval. Un departement trouve
         seulement par le repli embeddings, moins fiable, n'est jamais
         utilise pour refuser : s'il n'est pas autorise, il est ignore et
         le controle d'acces par chunk s'applique seul ;
      4. departement sans corpus reel : refus si explicite ; si detecte
         automatiquement, aucun filtre n'est applique (la detection ne doit
         pas bloquer a tort une question dont la reponse est ailleurs) ;
      5. question multi-indicateurs -> process_comparative_question() ;
      6. pipeline RAG ; si un departement DETECTE ne donne rien (retrieval
         vide), une seconde passe sans filtre de departement est tentee
         (le controle d'acces par chunk s'applique dans les deux cas).
    """

    explicite = selected_department if selected_department in DEPARTEMENTS else None

    if explicite:
        departement, origine_detection = explicite, "force"
    else:
        departement = detect_department(query, user_role)
        origine_detection = "mots-cles"

        if departement is None:
            departement = detect_department_embeddings(query, model, user_role)
            origine_detection = "embeddings"

            # Repli moins fiable : jamais utilise pour REFUSER l'acces.
            if department_access_denied(user_role, departement):
                _dbg(
                    f"Departement {departement!r} (embeddings) hors perimetre "
                    f"du role {user_role!r} : ignore."
                )
                departement = None

    _dbg(
        f"Departement : {departement!r} ({origine_detection}) "
        f"| role={user_role!r}"
    )

    multi = len(detect_intents(query)) >= 2

    est_definition = any(
        _norm(query).strip().startswith(p) for p in PREFIXES_GENERAUX
    )
    force_rag = (
        origine_detection in ("mots-cles", "force")
        and departement is not None
        and not est_definition
    )

    if detect_intent(query) == "generale" and not multi and not force_rag:
        return _resultat(
            generate_general_answer(query, departement), "GENERAL", "GENERALE",
            departement=departement,
        )

    if department_access_denied(user_role, departement):
        _dbg(
            f"Acces departement refuse : role={user_role!r} "
            f"autorises={sorted(user_allowed_departments(user_role))}"
        )
        return _resultat(
            message_refus_acces(user_role, departement=departement),
            "HORS_PERIMETRE", "HORS_PERIMETRE", departement=departement,
        )

    # Departement detecte, conserve pour l'affichage et le vocabulaire de la
    # reponse meme si le filtre de perimetre est desactive ci-dessous.
    departement_detecte = departement

    if departement and not departement_a_corpus_reel(metadata, departement):

        if explicite:
            return _resultat(
                MESSAGE_DEPARTEMENT_VIDE.format(
                    dept=LIBELLE_DEPARTEMENT[departement]
                ),
                "ABSENT", "ABSENTE", departement=departement,
            )

        _dbg(f"Departement detecte {departement!r} sans corpus reel : pas de filtre.")
        departement = None

    if multi:
        result = process_comparative_question(
            query, model, index, metadata, user_role,
            selected_department=explicite,
        )
        result["departement"] = departement_detecte
        return result

    result = _pipeline_rag(
        query, model, index, metadata, user_role, departement,
        departement_contexte=departement_detecte,
    )

    if (
        departement and not explicite
        and result["mode"] in ("ABSENT", "GENERAL")
        and not result["all_results"]
    ):
        _dbg("Aucun resultat avec le filtre de departement : seconde passe sans filtre.")
        result = _pipeline_rag(
            query, model, index, metadata, user_role, None,
            departement_contexte=departement_detecte,
        )

    result["departement"] = departement_detecte
    return result


# ============================================================================
# Audits et diagnostics
# ============================================================================

def audit_allowed_roles(metadata: list) -> None:
    """Couverture RBAC effective par entreprise."""
    entreprises: dict = {}

    for chunk in metadata:
        if chunk.get("type_document", "entreprise") == "public_reglementaire":
            continue
        entreprises.setdefault(chunk.get("entreprise", "?"), []).append(chunk)

    if not entreprises:
        return

    print("\nAudit RBAC effectif par entreprise :")

    for ent in sorted(entreprises):
        chunks = entreprises[ent]
        counts = Counter(
            role for c in chunks for role in effective_allowed_roles(c)
        )
        detail = ", ".join(f"{r}={counts.get(r, 0)}" for r in ROLES_DISPONIBLES)
        print(f"   {ent} ({len(chunks)} chunks) : {detail}")

    print("\nPolitique RBAC par entreprise :")
    for ent, roles in RBAC_POLICY.items():
        print(f"   {ent} -> {', '.join(sorted(roles))}")
    print()


def extended_audit_allowed_roles(metadata: list) -> list:
    """Audit RBAC effectif par DEPARTEMENT (un chunk multi-departements
    compte dans chacun). Retourne la liste des departements SANS document
    d'entreprise reel."""
    print("\nAudit RBAC effectif par département :")

    par_dept = {d: [] for d in DEPARTEMENTS}
    orphelins = 0

    for chunk in metadata:
        deps = departements_du_chunk(chunk)

        for d in deps:
            par_dept[d].append(chunk)

        if (
            not deps
            and chunk.get("type_document", "entreprise") != "public_reglementaire"
            and chunk.get("entreprise") not in RBAC_POLICY
        ):
            orphelins += 1

    for dept in DEPARTEMENTS:
        chunks = par_dept[dept]

        if not chunks:
            print(f"   {dept:10s} : 0 chunk indexé  /!\\ aucun document (data/{dept}/)")
            continue

        counts = Counter(
            role for c in chunks for role in effective_allowed_roles(c)
        )
        n_synth = sum(1 for c in chunks if c.get("is_synthetic"))
        n_regl = sum(
            1 for c in chunks
            if not c.get("is_synthetic")
            and c.get("type_document", "entreprise") == "public_reglementaire"
        )
        n_reel = len(chunks) - n_synth - n_regl

        alertes = []

        if counts.get(dept, 0) == 0:
            alertes.append("le rôle du département n'a accès à aucun de ses chunks")
        if n_synth == len(chunks):
            alertes.append("uniquement des données de démonstration")
        elif n_reel == 0:
            alertes.append("aucun document interne réel (textes réglementaires seulement)")

        detail = ", ".join(f"{r}={counts.get(r, 0)}" for r in ROLES_DISPONIBLES)
        alerte_txt = f"  /!\\ {' ; '.join(alertes)}" if alertes else ""

        print(
            f"   {dept:10s} ({len(chunks)} chunks : entreprise={n_reel}, "
            f"réglementaire={n_regl}, démo={n_synth}) : {detail}{alerte_txt}"
        )

    if orphelins:
        print(
            f"\n   /!\\ {orphelins} chunk(s) sans département ni entreprise "
            "couverte par RBAC_POLICY : droits dépendant uniquement de "
            "'allowed_roles' brut."
        )

    print("\nPolitique RBAC par département :")
    for dept, roles in DEPARTMENT_ACCESS_ROLES.items():
        print(f"   {dept} -> {', '.join(sorted(roles))}")
    print()

    return [d for d in DEPARTEMENTS if not departement_a_corpus_reel(metadata, d)]


def _apercu(content: str, taille: int = 160) -> str:
    return " ".join((content or "").split())[:taille]


def diagnostic_article(metadata: list, numero: str) -> None:
    """Le TEXTE de l'article existe-t-il dans l'index (ou seulement des
    renvois) ?"""
    titres, renvois = [], []

    for c in metadata:
        content = c.get("content", "")

        if not est_renvoi_article(content, numero):
            continue

        entree = (c.get("fichier_source"), c.get("page"), _apercu(content))
        (titres if est_titre_article(content, numero) else renvois).append(entree)

    print(f"\n{'=' * 60}\nDIAGNOSTIC : article {numero}\n{'=' * 60}")
    print(f"\nChunks portant le TITRE de l'article : {len(titres)}")

    for fichier, page, extrait in titres[:5]:
        print(f"  - {fichier} p.{page}\n    {extrait}")

    print(f"\nChunks contenant seulement un RENVOI : {len(renvois)}")

    for fichier, page, extrait in renvois[:5]:
        print(f"  - {fichier} p.{page}\n    {extrait}")

    if not titres:
        print(
            "\n/!\\ Aucun chunk ne porte le texte de cet article : le problème "
            "est en amont, dans le chunking du PDF."
        )

    print()


def diagnostic_terme(metadata: list, terme: str) -> None:
    """Cherche un terme metier dans TOUT l'index, hors scoring et RBAC."""
    motif = _motif_terme(terme)
    trouvailles = [c for c in metadata if motif.search(c.get("content", ""))]

    print(f"\n{'=' * 60}\nDIAGNOSTIC TERME : \"{terme}\"\n{'=' * 60}")
    print(f"\n{len(trouvailles)} chunk(s) contenant ce terme (ou variante) :")

    for c in trouvailles[:10]:
        texte = " ".join(c.get("content", "").split())
        m = motif.search(texte)
        debut = max(0, (m.start() if m else 0) - 60)

        print(
            f"  - {c.get('fichier_source')} p.{c.get('page')} "
            f"[{c.get('entreprise')}] (type={c.get('type_document', '?')}, "
            f"departement={c.get('departement', '?')}, "
            f"roles={c.get('allowed_roles', [])})"
            f"\n    ...{texte[debut:debut + 200]}..."
        )

    if not trouvailles:
        print(
            "\n/!\\ Aucun chunk ne contient ce terme : vérifie l'orthographe "
            "dans le document source ou l'absence réelle de l'information."
        )

    print()


def diagnostic_departement(metadata: list, dept: str) -> None:
    """Chunks rattaches a un departement, roles effectifs et extraits."""
    dept = dept.strip().lower()

    print(f"\n{'=' * 60}\nDIAGNOSTIC DEPARTEMENT : \"{dept}\"\n{'=' * 60}")

    if dept not in DEPARTEMENTS:
        print(f"/!\\ Département inconnu. Disponibles : {DEPARTEMENTS}\n")
        return

    chunks = [c for c in metadata if dept in departements_du_chunk(c)]
    print(f"\n{len(chunks)} chunk(s) rattaché(s) au département '{dept}'.")

    if not chunks:
        print(f"/!\\ Aucun chunk : corpus probablement non ingéré (data/{dept}/).\n")
        return

    print(f"Rôles attendus par défaut : {sorted(DEPARTMENT_ACCESS_ROLES[dept])}")

    for c in chunks[:8]:
        if c.get("is_synthetic"):
            nature = "DEMO"
        elif c.get("type_document", "entreprise") == "public_reglementaire":
            nature = "réglementaire"
        else:
            nature = "entreprise"

        print(
            f"  - [{nature}] {c.get('fichier_source')} p.{c.get('page')} "
            f"roles_effectifs={sorted(effective_allowed_roles(c))}"
            f"\n    ...{_apercu(c.get('content', ''))}..."
        )

    print()


# ============================================================================
# Evaluation du RAG (jeu de questions de reference)
# ============================================================================
#
# Le jeu de donnees est un fichier JSON : une liste de cas, ou un objet
# {"cas": [...]}. Chaque cas :
#
#   {
#     "id": "wafa_ca_2025",
#     "role": "finance",                       # role simule (defaut : tous)
#     "question": "Quel est le chiffre d'affaires de Wafa Assurance en 2025 ?",
#     "expected_mode": "RAG",                  # ou liste : ["RAG", "ABSENT"]
#                                              # RAG | MULTI_INTENT | GENERAL |
#                                              # ABSENT | HORS_PERIMETRE |
#                                              # CLARIFICATION
#     "expected_source": "Wafa_Assurance_RFA_2025.pdf",   # optionnel
#     "expected_contains": ["12 738"],         # optionnel (espaces ignores)
#                                              # Un element peut etre une LISTE
#                                              # d'alternatives acceptees :
#                                              # [["12 738", "12,738"], "MDH"]
#                                              # = (12 738 OU 12,738) ET MDH
#     "expected_not_contains": ["France"],     # optionnel
#     "expected_departement": "finance",       # optionnel
#     "forcer_departement": "finance"          # optionnel (forcage explicite)
#   }
#
# Un cas est REUSSI si toutes les verifications applicables passent. Un cas
# SANS aucune attente (pas d'expected_*) est "non evalue" : il n'entre pas
# dans le taux de reussite, mais son resultat est affiche pour permettre de
# le CALIBRER (fixer ensuite expected_* a la valeur observee si elle est
# correcte, ou signaler un bug). Les
# indicateurs sont des PROXYS simples et reproductibles des metriques RAG
# classiques :
#   - retrieval_hit  : la source attendue figure dans le retrieval brut
#                      (proxy de "retrieval precision / context recall") ;
#   - contexte_hit   : la source attendue figure dans le contexte final
#                      envoye au generateur ;
#   - contenu        : la valeur attendue figure dans la reponse
#                      (proxy de "faithfulness" / exactitude) ;
#   - citations      : une reponse RAG cite au moins une source ;
#   - refus corrects / faux refus : qualite du controle d'acces.

EVAL_DIR = Path("data/eval")


def _liste(valeur) -> list:
    if valeur is None:
        return []
    return list(valeur) if isinstance(valeur, (list, tuple)) else [valeur]


def _compact(text: str) -> str:
    """Texte sans accents, en minuscules, SANS espaces (compare "12 738" et
    "12738" ou "12\u00a0738")."""
    return re.sub(r"\s+", "", _norm(text))


def _fichiers_contexte(result: dict) -> set:
    """Fichiers du contexte final (et des sources citees), y compris pour
    les questions multi-indicateurs."""
    fichiers = {r.get("fichier_source") for r in result.get("candidats_finaux", [])}
    fichiers |= {r.get("fichier_source") for _, r in result.get("cited_sources", [])}

    for sr in result.get("sous_reponses", []):
        fichiers |= _fichiers_contexte(sr["result"])

    fichiers.discard(None)
    return fichiers


def _fichiers_retrieval(result: dict) -> set:
    """Fichiers du retrieval brut (avant reclassement et garde-fous)."""
    fichiers = {r.get("fichier_source") for r in result.get("all_results", [])}

    for sr in result.get("sous_reponses", []):
        fichiers |= _fichiers_retrieval(sr["result"])

    fichiers.discard(None)
    return fichiers


def charger_jeu_evaluation(chemin) -> list:
    with open(chemin, "r", encoding="utf-8") as f:
        data = json.load(f)

    cas = data.get("cas", []) if isinstance(data, dict) else data

    if not isinstance(cas, list) or not cas:
        raise ValueError(f"Jeu d'evaluation vide ou invalide : {chemin}")

    for c in cas:
        if "question" not in c:
            raise ValueError(f"Cas sans 'question' : {c.get('id', c)}")

        if c.get("role", "tous") not in ROLES_DISPONIBLES:
            raise ValueError(f"Role inconnu dans le cas {c.get('id')}: {c.get('role')}")

    return cas


def evaluer_cas(cas: dict, model, index, metadata) -> dict:
    """Execute UN cas dans le pipeline reel et calcule ses verifications."""
    role = cas.get("role", "tous")
    attendus = _liste(cas.get("expected_mode"))

    debut = time.perf_counter()
    erreur, result = None, None

    try:
        result = process_question_hybride(
            cas["question"], model, index, metadata, role,
            selected_department=cas.get("forcer_departement"),
        )
    except Exception as e:
        erreur = f"{type(e).__name__}: {e}"

    latence = time.perf_counter() - debut

    sortie = {
        "id": cas.get("id", cas["question"][:40]),
        "role": role,
        "question": cas["question"],
        "attendus": attendus,
        "mode": None,
        "verifs": {},
        "infos": {},
        "passe": False,
        "latence_s": round(latence, 2),
        "confiance": None,
        "departement": None,
        "reponse": "",
        "erreur": erreur,
    }

    if result is None:
        return sortie

    mode = result["mode"]
    verifs, infos = {}, {}

    if attendus:
        verifs["mode"] = mode in attendus

    source = cas.get("expected_source")

    if source:
        infos["retrieval"] = source in _fichiers_retrieval(result)
        # Le contexte final n'a de sens que si le pipeline a REELLEMENT
        # produit une reponse sourcee (RAG/MULTI_INTENT). En CLARIFICATION,
        # ABSENT, GENERAL ou HORS_PERIMETRE, il n'y a pas de contexte a citer.
        if mode in ("RAG", "MULTI_INTENT"):
            verifs["contexte"] = source in _fichiers_contexte(result)

    reponse_compacte = _compact(result.get("answer", ""))

    def _present(valeur) -> bool:
        """Chaine, ou liste d'ALTERNATIVES dont une suffit."""
        return any(_compact(v) in reponse_compacte for v in _liste(valeur))

    contient = _liste(cas.get("expected_contains"))
    if contient:
        verifs["contenu"] = all(_present(c) for c in contient)

    interdit = _liste(cas.get("expected_not_contains"))
    if interdit:
        verifs["interdit"] = not any(_present(c) for c in interdit)

    if cas.get("expected_departement"):
        verifs["departement"] = result.get("departement") == cas["expected_departement"]

    if mode in ("RAG", "MULTI_INTENT") and any(
        a in ("RAG", "MULTI_INTENT") for a in attendus
    ):
        verifs["citations"] = bool(result.get("cited_sources"))

    sortie.update({
        "mode": mode,
        "verifs": verifs,
        "infos": infos,
        "passe": all(verifs.values()) if verifs else None,
        "confiance": round(result.get("confidence", 0.0), 2),
        "departement": result.get("departement"),
        "reponse": (result.get("answer") or "")[:600],
    })

    return sortie


def _taux(valeurs) -> float | None:
    valeurs = list(valeurs)
    if not valeurs:
        return None
    return round(100.0 * sum(1 for v in valeurs if v) / len(valeurs), 1)


def resumer_evaluation(resultats: list) -> dict:
    """Indicateurs agreges (pourcentages ; None = non applicable)."""
    latences = sorted(r["latence_s"] for r in resultats)
    p95 = latences[min(len(latences) - 1, int(0.95 * len(latences)))] if latences else None

    avec_refus_attendu = [r for r in resultats if "HORS_PERIMETRE" in r["attendus"]]
    sans_refus_attendu = [
        r for r in resultats if r["attendus"] and "HORS_PERIMETRE" not in r["attendus"]
    ]

    return {
        "nb_cas": len(resultats),
        "nb_erreurs": sum(1 for r in resultats if r["erreur"]),
        "nb_non_evalues": sum(
            1 for r in resultats if r["passe"] is None and not r["erreur"]
        ),
        "taux_reussite": _taux(
            r["passe"] for r in resultats if r["passe"] is not None
        ),
        "exactitude_mode": _taux(
            r["verifs"]["mode"] for r in resultats if "mode" in r["verifs"]
        ),
        "retrieval_hit": _taux(
            r["infos"]["retrieval"] for r in resultats if "retrieval" in r["infos"]
        ),
        "contexte_hit": _taux(
            r["verifs"]["contexte"] for r in resultats if "contexte" in r["verifs"]
        ),
        "exactitude_contenu": _taux(
            r["verifs"]["contenu"] for r in resultats if "contenu" in r["verifs"]
        ),
        "citations": _taux(
            r["verifs"]["citations"] for r in resultats if "citations" in r["verifs"]
        ),
        "refus_corrects": _taux(r["mode"] == "HORS_PERIMETRE" for r in avec_refus_attendu),
        "faux_refus": _taux(r["mode"] == "HORS_PERIMETRE" for r in sans_refus_attendu),
        "latence_moyenne_s": (
            round(sum(latences) / len(latences), 2) if latences else None
        ),
        "latence_p95_s": p95,
    }


_LIBELLES_RESUME = [
    ("taux_reussite", "Taux de reussite global (%)"),
    ("exactitude_mode", "Mode attendu obtenu (%)"),
    ("retrieval_hit", "Source attendue dans le retrieval (%)"),
    ("contexte_hit", "Source attendue dans le contexte final (%)"),
    ("exactitude_contenu", "Valeur attendue dans la reponse (%)"),
    ("citations", "Reponses RAG avec citation (%)"),
    ("refus_corrects", "Refus d'acces corrects (%)"),
    ("faux_refus", "Faux refus d'acces (%, plus bas = mieux)"),
    ("latence_moyenne_s", "Latence moyenne (s)"),
    ("latence_p95_s", "Latence p95 (s)"),
    ("nb_non_evalues", "Cas non evalues (a calibrer)"),
    ("nb_erreurs", "Cas en erreur"),
]


def afficher_resume_evaluation(resume: dict) -> None:
    print(f"\n{'=' * 60}\nRESUME DE L'EVALUATION ({resume['nb_cas']} cas)\n{'=' * 60}")

    for cle, libelle in _LIBELLES_RESUME:
        valeur = resume.get(cle)
        print(f"  {libelle:46s} {'n/a' if valeur is None else valeur}")

    print()


def _snapshot_configuration() -> dict:
    """Parametres qui influencent les resultats : permet d'expliquer l'ecart
    entre deux rapports (v1 vs v2)."""
    return {
        "groq_model": GROQ_MODEL,
        "groq_verify_model": GROQ_VERIFY_MODEL,
        "verify_chars": VERIFY_CHARS,
        "embedding_model": MODEL_NAME,
        "top_k_retrieval": TOP_K_RETRIEVAL,
        "top_k_verify": TOP_K_VERIFY,
        "top_k_context": TOP_K_CONTEXT,
        "poids_faiss": POIDS_FAISS,
        "poids_lexical": POIDS_LEXICAL,
        "seuil_detection_departement": SEUIL_DETECTION_DEPARTEMENT,
        "seuil_embedding_departement": SEUIL_EMBEDDING_DEPARTEMENT,
        "marge_embedding_departement": MARGE_EMBEDDING_DEPARTEMENT,
    }


def run_evaluation(
    chemin, model, index, metadata,
    label: str = "run", out_dir: Path = EVAL_DIR, pause: float = 0.0,
    ids: list | None = None,
) -> dict:
    """Rejoue tout le jeu de questions, affiche le detail et le resume, et
    sauvegarde un rapport JSON horodate (comparable via --eval-compare)."""
    cas_liste = charger_jeu_evaluation(chemin)

    if ids:
        cas_liste = [
            c for c in cas_liste
            if any(c.get("id", "").startswith(p) for p in ids)
        ]
        if not cas_liste:
            raise ValueError(f"Aucun cas ne correspond a --eval-ids {ids}")

    print(f"\nEvaluation '{label}' : {len(cas_liste)} cas depuis {chemin}\n")

    resultats = []

    for i, cas in enumerate(cas_liste, start=1):
        r = evaluer_cas(cas, model, index, metadata)
        resultats.append(r)

        echecs = [k for k, v in r["verifs"].items() if not v]

        if r["erreur"] or r["passe"] is False:
            statut = "KO"
        elif r["passe"] is None:
            statut = "--"
        else:
            statut = "OK"

        if r["erreur"]:
            detail = f"erreur={r['erreur']}"
        elif r["passe"] is None:
            detail = "non evalue (aucune attente definie)"
        else:
            detail = f"echecs={echecs}" if echecs else ""

        print(
            f"[{statut}] {i:02d}/{len(cas_liste):02d} {r['id']:32s} "
            f"role={r['role']:9s} mode={r['mode']!s:15s} "
            f"{r['latence_s']:5.1f}s {detail}"
        )

        if r["passe"] is None and not r["erreur"]:
            print(f"        reponse : {' '.join(r['reponse'].split())[:200]}")

        sys.stdout.flush()

        if r["erreur"] and r["erreur"].startswith("QuotaError"):
            print(
                "\n/!\\ Quota Groq épuisé : évaluation interrompue. "
                "Relancez après réinitialisation du quota."
            )
            break

        if pause and i < len(cas_liste):
            time.sleep(pause)

    resume = resumer_evaluation(resultats)
    afficher_resume_evaluation(resume)

    echoues = [r for r in resultats if r["passe"] is False or r["erreur"]]
    non_evalues = [r for r in resultats if r["passe"] is None and not r["erreur"]]

    if non_evalues:
        print("Cas non evalues (a calibrer : fixez expected_* avec la valeur observee) :")
        for r in non_evalues:
            print(f"  - {r['id']} : mode obtenu={r['mode']}")
        print()

    if echoues:
        print("Cas echoues (attendu -> obtenu) :")
        for r in echoues:
            print(f"  - {r['id']} : attendu={r['attendus']} obtenu={r['mode']}")
        print()

    rapport = {
        "label": label,
        "date": datetime.now().isoformat(timespec="seconds"),
        "jeu_de_donnees": str(chemin),
        "configuration": _snapshot_configuration(),
        "resume": resume,
        "cas": resultats,
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nom = f"eval_{re.sub(r'[^A-Za-z0-9_-]+', '_', label)}_{datetime.now():%Y%m%d_%H%M%S}.json"
    chemin_rapport = out_dir / nom

    with open(chemin_rapport, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    print(f"Rapport enregistre : {chemin_rapport}\n")
    return rapport


def comparer_rapports(chemin_a, chemin_b) -> None:
    """Compare deux rapports d'evaluation (A = avant, B = apres)."""
    with open(chemin_a, "r", encoding="utf-8") as f:
        a = json.load(f)
    with open(chemin_b, "r", encoding="utf-8") as f:
        b = json.load(f)

    print(f"\n{'=' * 60}")
    print(f"COMPARAISON : A='{a.get('label')}' ({a.get('date')})")
    print(f"              B='{b.get('label')}' ({b.get('date')})")
    print(f"{'=' * 60}")

    conf_a, conf_b = a.get("configuration", {}), b.get("configuration", {})
    diff_conf = {
        k: (conf_a.get(k), conf_b.get(k))
        for k in sorted(set(conf_a) | set(conf_b))
        if conf_a.get(k) != conf_b.get(k)
    }

    if diff_conf:
        print("\nParametres modifies :")
        for k, (va, vb) in diff_conf.items():
            print(f"  {k}: {va} -> {vb}")

    print(f"\n{'Indicateur':46s} {'A':>8s} {'B':>8s} {'ecart':>8s}")

    for cle, libelle in _LIBELLES_RESUME:
        va, vb = a["resume"].get(cle), b["resume"].get(cle)
        ecart = (
            f"{vb - va:+.1f}"
            if isinstance(va, (int, float)) and isinstance(vb, (int, float))
            else ""
        )
        print(
            f"{libelle:46s} {'n/a' if va is None else va:>8} "
            f"{'n/a' if vb is None else vb:>8} {ecart:>8}"
        )

    cas_a = {c["id"]: c for c in a.get("cas", [])}
    cas_b = {c["id"]: c for c in b.get("cas", [])}

    regressions = [
        i for i in cas_a
        if i in cas_b
        and cas_a[i]["passe"] is True and cas_b[i]["passe"] is False
    ]
    ameliorations = [
        i for i in cas_a
        if i in cas_b
        and cas_a[i]["passe"] is False and cas_b[i]["passe"] is True
    ]

    print(f"\nAmeliorations (KO -> OK) : {ameliorations or 'aucune'}")
    print(f"Regressions   (OK -> KO) : {regressions or 'aucune'}\n")


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Assistant RAG sécurisé (RBAC + détection automatique du département)."
    )
    parser.add_argument(
        "--role", choices=ROLES_DISPONIBLES, default=None,
        help="Rôle utilisateur (sinon RAG_USER_ROLE, sinon demandé une fois).",
    )
    parser.add_argument(
        "--departement", choices=DEPARTEMENTS, default=None,
        help="Forçage OPTIONNEL du département (sinon détection automatique).",
    )
    parser.add_argument(
        "--strict-audit", action="store_true",
        help="Quitte en erreur si un département n'a aucun document réel.",
    )
    parser.add_argument(
        "--question", default=None,
        help="Question unique en mode non interactif (Streamlit, scripts).",
    )
    parser.add_argument(
        "--eval", default=None, metavar="JEU.json",
        help="Rejoue un jeu de questions de reference et mesure la qualite.",
    )
    parser.add_argument(
        "--eval-label", default="run",
        help="Nom de l'execution d'evaluation (ex: v1, v2-chunking).",
    )
    parser.add_argument(
        "--eval-out", default=str(EVAL_DIR),
        help="Dossier des rapports d'evaluation (defaut : data/eval).",
    )
    parser.add_argument(
        "--eval-pause", type=float, default=0.0,
        help="Pause (secondes) entre deux cas, si l'API limite le debit.",
    )
    parser.add_argument(
        "--eval-ids", default=None,
        help="Prefixes d'id separes par des virgules (ex: wafa_resultat,jur_) : "
             "ne rejoue que ces cas.",
    )
    parser.add_argument(
        "--eval-compare", nargs=2, metavar=("AVANT.json", "APRES.json"),
        default=None,
        help="Compare deux rapports d'evaluation et quitte.",
    )
    return parser.parse_args()


def resolve_role(args, interactive: bool) -> str:
    """Role : argument CLI > RAG_USER_ROLE > prompt (une seule fois) > 'tous'."""
    if args.role:
        return args.role

    env_role = os.getenv("RAG_USER_ROLE", "").strip().lower()
    if env_role in ROLES_DISPONIBLES:
        return env_role

    if interactive:
        role = input(f"Rôle simulé {ROLES_DISPONIBLES} : ").strip().lower()
        if role in ROLES_DISPONIBLES:
            return role
        print("Rôle inconnu, utilisation de 'tous' par défaut.")

    return "tous"


def resolve_department_override(args) -> str | None:
    """Forçage optionnel du departement (jamais demande interactivement)."""
    if args.departement:
        return args.departement

    env_dept = os.getenv("RAG_USER_DEPARTMENT", "").strip().lower()
    return env_dept if env_dept in DEPARTEMENTS else None


def _afficher_resultat(result: dict) -> None:
    libelles = {
        "RAG": "Réponse issue des documents autorisés",
        "GENERAL": "Réponse générale",
        "ABSENT": "Information absente",
        "HORS_PERIMETRE": "Accès non autorisé",
        "MULTI_INTENT": "Comparaison multi-indicateurs",
        "CLARIFICATION": "Précision nécessaire",
    }

    print(f"\n{'=' * 60}")
    print(f"RÉPONSE - {libelles.get(result['mode'], result['mode'])}")

    if result.get("departement"):
        print(f"Département détecté : {LIBELLE_DEPARTEMENT[result['departement']]}")

    print(f"{'=' * 60}")
    print(result["answer"])

    if result["cited_sources"] or result["mode"] == "RAG":
        print(f"\n{'=' * 60}\nSOURCES UTILISÉES\n{'=' * 60}")

        if result["cited_sources"]:
            for i, r in result["cited_sources"]:
                tag = " [DEMO]" if r["is_synthetic"] else ""
                dep = f" [{r.get('departement')}]" if r.get("departement") else ""
                print(
                    f"[{i}] {_nom_source(r)} - {r['fichier_source']} - "
                    f"p.{r['page']}{dep}{tag}"
                )
        else:
            print("Aucune source explicitement citée dans la réponse.")

    if result.get("incoherence_citation"):
        print(
            "\n/!\\ Réponse sans citation : des extraits étaient disponibles "
            "mais aucune source n'a été citée. À vérifier avant diffusion."
        )

    if not DEBUG:
        return

    print(
        f"\n[Debug] Mode={result['mode']} Score={result['max_score']:.3f} "
        f"can_answer={result.get('can_answer')} "
        f"confidence={result.get('confidence', 0):.2f} "
        f"verify_error={result.get('verify_error')} "
        f"extraits={result.get('extraits_verifier')} "
        f"departement={result.get('departement')!r}"
    )

    m = result.get("montant_structure")
    if m:
        print(
            f"[Debug] Montant structuré : {m['valeur']:g} {m['unite']} "
            f"(metric={m['metric']}, scope={m['scope']})"
        )

    for sr in result.get("sous_reponses", []):
        print(
            f"[Debug] Sous-question {sr['subquery']!r} -> "
            f"can_answer={sr['result'].get('can_answer')} montant={sr['montant']}"
        )

    for titre, liste in (
        ("Classement final (envoyé au générateur)", result.get("candidats_finaux")),
        ("Retrieval brut", result.get("all_results")),
    ):
        if not liste:
            continue

        print(f"\n[Debug] {titre} :")

        for i, r in enumerate(liste[:5], start=1):
            print(
                f"  {i}. score={r['score']:.3f} "
                f"reclasse={r.get('_score_reclasse', r['score']):.3f} "
                f"(f={r['_faiss_score']:.2f} l={r['_lexical_score']:.2f}) | "
                f"{r['entreprise']} | p.{r['page']} | {r['fichier_source']}"
                f"{' | TITRE_ART' if r.get('_article_titre') else ''}"
            )


def main():
    args = parse_args()

    if args.eval_compare:
        comparer_rapports(*args.eval_compare)
        return

    print("Chargement de l'index...")
    index, metadata = load_index()
    print(f"{index.ntotal} chunks disponibles.\n")

    print("Répartition par type de document :")
    for type_doc, n in Counter(
        c.get("type_document", "ABSENT") for c in metadata
    ).items():
        print(f"   {type_doc}: {n} chunks ({(n / len(metadata)) * 100:.1f}%)")

    audit_allowed_roles(metadata)
    departements_vides = extended_audit_allowed_roles(metadata)

    if departements_vides:
        print(
            f"/!\\ ATTENTION : {len(departements_vides)} département(s) sans "
            f"document d'entreprise réel : {departements_vides}"
        )

        if args.strict_audit:
            print(
                "\n--strict-audit : arrêt. Ingérez les documents réels de ces "
                "départements (data/<dept>/) avant de relancer."
            )
            sys.exit(1)

    print("Chargement du modèle d'embeddings...")
    model = SentenceTransformer(MODEL_NAME)

    if args.eval:
        run_evaluation(
            args.eval, model, index, metadata,
            label=args.eval_label, out_dir=Path(args.eval_out),
            pause=args.eval_pause,
            ids=[p.strip() for p in args.eval_ids.split(",") if p.strip()]
            if args.eval_ids else None,
        )
        return

    interactive = sys.stdin.isatty() and not args.question
    role = resolve_role(args, interactive)
    forcage = resolve_department_override(args)

    print(f"\nRôle : {role} | Département : "
          f"{forcage or 'détection automatique'}")

    if args.question:
        try:
            result = process_question_hybride(
                args.question, model, index, metadata, role,
                selected_department=forcage,
            )
        except QuotaError:
            print(f"\n{MESSAGE_QUOTA}")
            return
        _afficher_resultat(result)
        return

    print(
        "\nCommandes :"
        "\n  diag <numero>       -> vérifie qu'un article existe dans l'index"
        "\n  terme <expression>  -> cherche un terme métier dans tout l'index"
        "\n  dept <nom>          -> diagnostic d'un département"
    )

    if not DEBUG:
        print("\n(RAG_DEBUG=1 pour afficher les détails techniques)")

    while True:
        query = input("\nVotre question (ou 'quit' pour sortir) : ").strip()

        if query.lower() in ("quit", "exit", ""):
            break

        for motif, fonction in (
            (r"diag\s+(\d+)", diagnostic_article),
            (r"terme\s+(.+)", diagnostic_terme),
            (r"dept\s+(.+)", diagnostic_departement),
        ):
            m = re.fullmatch(motif, query, flags=re.IGNORECASE)
            if m:
                fonction(metadata, m.group(1).strip())
                break
        else:
            print("\nTraitement de la question...")
            try:
                result = process_question_hybride(
                    query, model, index, metadata, role,
                    selected_department=forcage,
                )
            except QuotaError:
                print(f"\n{MESSAGE_QUOTA}")
                continue
            _afficher_resultat(result)


if __name__ == "__main__":
    main()