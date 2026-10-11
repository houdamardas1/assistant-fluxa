#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLASSIFIER ENTREPRISE DEPARTEMENTS v9.3 (corrigé complet)

Objectif
--------
Classer UNIQUEMENT les chunks :
    type_document == "entreprise"

Départements :
    direction
    finance
    it
    rh
    commerce
    juridique
    marketing

IMPORTANT
---------
Ce script NE MODIFIE PAS :
    - FAISS
    - RBAC
    - allowed_roles
    - access_roles
    - departement (singulier)
    - type_document
    - les chunks public_reglementaire

Il modifie uniquement :
    - departements
    - departements_source
    - departements_termes

Mode par défaut :
    DRY-RUN

Application :
    python "classify_enterprise_departments.py" --apply

CORRECTIFS v9.1 (par rapport à v9)
-----------------------------------
1. finance_exclue() ne retire plus TOUT le score "bilan" du chunk dès
   qu'une expression exclue (ex: "bilan carbone") apparaît quelque part
   dans le texte. On soustrait maintenant uniquement les occurrences
   réellement rattachées à l'expression exclue.
2. finance_macro_exclue() était définie mais jamais appelée : elle est
   maintenant branchée dans validation_finance (rejette un chunk macro-
   économique générique qui n'a par ailleurs aucun terme "fort").
3. Ajout d'un fallback "contexte_*" pour IT, commerce et marketing,
   symétrique à celui qui existait déjà pour direction/finance/rh, afin
   de réduire l'asymétrie qui gonflait artificiellement les non-classés
   sur ces trois départements.
4. Quelques seuils de répétition légèrement abaissés (donnee, innovation,
   marche, communication) car plusieurs chunks réels ratent le seuil de
   justesse (voir CHANGELOG en bas de fichier).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any


# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_METADATA_PATH = (
    BASE_DIR
    / "data"
    / "index"
    / "metadata.json"
)

SOURCE_TAG = "classifier_v9_3"

DEPARTEMENTS = [
    "direction",
    "finance",
    "it",
    "rh",
    "commerce",
    "juridique",
    "marketing",
]

SEUIL_PRIMAIRE = 3.0
SEUIL_REPETITION = 3.0
SEUIL_SECOND_DEPT = 5.0
RATIO_SECOND_DEPT = 0.82
MAX_DEPTS = 2
MIN_TERMES_DISTINCTS = 2


# ============================================================================
# VOCABULAIRE DIRECTION
# ============================================================================

DIRECTION_FORTS = {
    "conseil d administration",
    "conseil de surveillance",
    "comite de direction",
    "comite d audit",
    "assemblee generale",
    "directeur general",
    "directrice generale",
    "administrateur",
    "comex",
    "plan strategique",
    "orientations strategiques",
    "feuille de route",
    "decision strategique",
}

DIRECTION_CONTEXTUELS = {
    "gouvernance",
    "strategie",
    "strategique",
    "ambition",
    "perspective",
    "mission",
    "vision",
}

DIRECTION_REPETITION = {
    "gouvernance": 3,
    "strategie": 3,
    "strategique": 3,
    "vision": 3,
    "mission": 4,
    "ambition": 3,
    "perspective": 3,
}


# ============================================================================
# VOCABULAIRE FINANCE
# ============================================================================

FINANCE_FORTS = {
    "pnb",
    "tresorerie",
    "bilan",
    "etat financier",
    "resultat net",
    "resultat d exploitation",
    "commissaire aux comptes",
    "immobilisation",
    "dividende",
    "emprunt",
    "provisions techniques",
    "rentabilite",
    "creance",
    "amortissement",
    "benefice",
    "chiffre d affaires",
    "passif",
    "actif",
    "compte de resultat",
    "compte annuel",
    "resultat financier",
    "charges financieres",
    "produits financiers",
    "capitaux propres",
    "fonds propres",
    "placements",
    "engagements techniques",
    "primes emises",
    "resultat technique",
    "sinistres",
    "marge de solvabilite",
    "produits de placement",
    "produits des placements",
    "charges techniques",
    "produits techniques",
    "provisions pour sinistres",
}

FINANCE_CONTEXTUELS = {
    "compte",
    "exercice",
    "financier",
    "comptable",
    "comptabilite",
    "resultat",
    "dette",
    "perte",
    "charge",
    "produit",
    "placement",
    "prime",
    "sinistre",
    "engagement",
    "technique",
}

FINANCE_REPETITION = {
    "bilan": 2,
    "compte": 3,
    "dette": 3,
    "resultat": 3,
    "financier": 3,
    "comptable": 3,
    "exercice": 4,
    "perte": 3,
}

FINANCE_PAIRS = {
    frozenset({"placement", "financier"}),
    frozenset({"prime", "resultat"}),
    frozenset({"engagement", "technique"}),
    frozenset({"charge", "produit"}),
    frozenset({"resultat", "technique"}),
    frozenset({"sinistre", "provision"}),
}

FINANCE_EXCLUSIONS = {
    "bilan carbone",
    "bilan energetique",
    "bilan environnemental",
    "bilan ges",
    "bilan emissions",
    "bilan climatique",
}

FINANCE_MACRO_EXCLUSIONS = {
    "pib",
    "inflation",
    "economie du senegal",
    "economie mondiale",
    "economie nationale",
    "zone cima",
    "taux directeur",
    "banque centrale",
    "marche mondial",
}


# ============================================================================
# VOCABULAIRE IT
# ============================================================================

IT_FORTS = {
    "systeme d information",
    "securite de l information",
    "securite des systemes d information",
    "cybersecurite",
    "smsi",
    "iso 27001",
    "data center",
    "base de donnees",
    "intelligence artificielle",
    "transformation digitale",
    "cloud",
    "infrastructure informatique",
    "reseau informatique",
    "logiciel",
    "architecture informatique",
    "infrastructure cloud",
}

IT_CONTEXTUELS = {
    "donnee",
    "numerique",
    "informatique",
    "innovation",
    "reseau",
    "application",
    "logiciel",
    "digital",
    "technologie",
    "systeme",
}

# CORRECTIF #4 : donnee et innovation abaissés de 4 -> 3
IT_REPETITION = {
    "application": 2,
    "logiciel": 2,
    "informatique": 2,
    "numerique": 2,
    "donnee": 3,
    "systeme": 4,
    "innovation": 3,
}

IT_DISCRIMINANTS = {
    "informatique",
    "numerique",
    "logiciel",
    "application",
    "donnee",
    "reseau",
    "systeme",
    "digital",
    "technologie",
}


# ============================================================================
# VOCABULAIRE RH
# ============================================================================

RH_FORTS = {
    "ressources humaines",
    "recrutement",
    "gestion des carrieres",
    "gpec",
    "masse salariale",
    "dialogue social",
    "absenteisme",
    "egalite professionnelle",
    "bien etre au travail",
    "sante et securite au travail",
    "accidents du travail",
    "embauche",
    "effectif",
}

RH_CONTEXTUELS = {
    "talent",
    "competence",
    "carriere",
    "collaborateur",
    "personnel",
    "salarie",
    "employe",
    "equipe",
    "formation",
    "remuneration",
    "mobilite",
    "parcours professionnel",
    "capital humain",
    "diversite",
    "inclusion",
    "travailleur",
    "stagiaire",
}

RH_REPETITION = {
    "collaborateur": 3,
    "personnel": 3,
    "employe": 3,
    "salarie": 3,
    "travailleur": 3,
    "effectif": 2,
    "formation": 3,
    "competence": 3,
    "carriere": 3,
    "talent": 3,
    "remuneration": 4,
    "equipe": 4,
    "inclusion": 3,
}

RH_PAIRS = {
    frozenset({"talent", "competence"}),
    frozenset({"talent", "remuneration"}),
    frozenset({"competence", "carriere"}),
    frozenset({"collaborateur", "formation"}),
    frozenset({"collaborateur", "personnel"}),
    frozenset({"formation", "competence"}),
    frozenset({"formation", "carriere"}),
    frozenset({"bien etre au travail", "collaborateur"}),
    frozenset({"sante et securite au travail", "collaborateur"}),
    frozenset({"effectif", "salarie"}),
}

RH_EXCLUSIONS = {
    "beneficiaire",
    "population couverte",
    "couverture maladie",
    "assurance maladie",
    "amo",
    "patient",
    "prescripteur",
    "ordonnance",
    "systeme de sante",
    "population",
}


# ============================================================================
# VOCABULAIRE COMMERCE
# ============================================================================

COMMERCE_FORTS = {
    "part de marche",
    "force de vente",
    "reseau commercial",
    "reseau de distribution",
    "canaux de distribution",
    "agents generaux",
    "commercialisation",
    "prospection",
    "developpement commercial",
    "portefeuille clients",
    "apres vente",
    "satisfaction client",
    "reclamation",
    "bancassurance",
    "offre commerciale",
}

COMMERCE_CONTEXTUELS = {
    "vente",
    "vehicule",
    "client",
    "clientele",
    "commercial",
    "commerciale",
    "distribution",
    "portefeuille",
    "produit",
    "agence",
    "commande",
    "prospect",
    "marche",
}

# CORRECTIF #4 : marche abaissé de 4 -> 3
COMMERCE_REPETITION = {
    "vente": 2,
    "vehicule": 2,
    "client": 3,
    "clientele": 2,
    "agence": 3,
    "portefeuille": 2,
    "distribution": 2,
    "marche": 3,
}

COMMERCE_PAIRS = {
    frozenset({"produit", "marche"}),
    frozenset({"produit", "vente"}),
    frozenset({"client", "vente"}),
    frozenset({"client", "commercial"}),
    frozenset({"clientele", "marche"}),
    frozenset({"agence", "client"}),
}


# ============================================================================
# VOCABULAIRE JURIDIQUE
# ============================================================================

JURIDIQUE_FORTS = {
    "conformite",
    "compliance",
    "contentieux",
    "litige",
    "acaps",
    "ammc",
    "cndp",
    "bank al maghrib",
    "donnees personnelles",
    "clauses",
    "clause",
    "risque juridique",
    "obligations legales",
    "fraude",
    "corruption",
    "lutte contre corruption",
    "blanchiment",
    "lcb ft",
    "sanctions",
    "donnee personnelle",
}

JURIDIQUE_CONTEXTUELS = {
    "contrat",
    "clause",
    "ethique",
    "deontologie",
    "droit",
    "reglementation",
    "legislation",
    "circulaire",
    "autorite de controle",
    "code",
    "juridique",
    "legal",
    "loi",
    "projet de loi",
    "dahir",
    "code des assurances",
    "code de la route",
    "indemnisation",
    "victime",
}

JURIDIQUE_REPETITION = {
    "contrat": 4,
    "clause": 3,
    "droit": 4,
    "reglementation": 3,
    "legislation": 3,
    "code": 4,
    "juridique": 3,
    "ethique": 3,
    "deontologie": 2,
}

JURIDIQUE_PAIRS = {
    frozenset({"contrat", "clause"}),
    frozenset({"contrat", "ethique"}),
    frozenset({"contrat", "deontologie"}),
    frozenset({"contrat", "droit"}),
    frozenset({"contrat", "reglementation"}),
    frozenset({"contrat", "legislation"}),
    frozenset({"contrat", "conformite"}),
    frozenset({"ethique", "deontologie"}),
    frozenset({"reglementation", "legislation"}),
}

JURIDIQUE_REPETITION_FORTS = {
    "corruption": 2,
    "fraude": 2,
    "litige": 2,
    "conformite": 2,
    "donnees personnelles": 2,
    "donnee personnelle": 2,
}


# ============================================================================
# VOCABULAIRE MARKETING
# ============================================================================

MARKETING_FORTS = {
    "image de marque",
    "notoriete",
    "campagne publicitaire",
    "campagne de communication",
    "publicite",
    "relations presse",
    "branding",
    "communication institutionnelle",
    "e reputation",
    "plan de communication",
    "identite de marque",
    "positionnement de marque",
}

MARKETING_CONTEXTUELS = {
    "marque",
    "communication",
    "campagne",
    "audience",
    "reputation",
    "positionnement",
}

# CORRECTIF #4 : communication abaissé de 4 -> 3
MARKETING_REPETITION = {
    "marque": 3,
    "communication": 3,
    "campagne": 3,
    "reputation": 2,
    "positionnement": 3,
}

MARKETING_PAIRS = {
    frozenset({"marque", "communication"}),
    frozenset({"marque", "positionnement"}),
    frozenset({"campagne", "communication"}),
    frozenset({"audience", "communication"}),
    frozenset({"reputation", "communication"}),
}


# ============================================================================
# ALIASES
# ============================================================================

ALIASES = {
    "comptes": "compte",
    "comptables": "comptable",
    "financiers": "financier",
    "resultats": "resultat",
    "exercices": "exercice",
    "dettes": "dette",
    "pertes": "perte",
    "bilans": "bilan",
    "creances": "creance",
    "immobilisations": "immobilisation",
    "benefices": "benefice",
    "actifs": "actif",
    "passifs": "passif",
    "dividendes": "dividende",
    "emprunts": "emprunt",

    "collaborateurs": "collaborateur",
    "employes": "employe",
    "salaries": "salarie",
    "travailleurs": "travailleur",
    "talents": "talent",
    "competences": "competence",
    "carrieres": "carriere",
    "formations": "formation",
    "remunerations": "remuneration",
    "equipes": "equipe",
    "effectifs": "effectif",
    "personnels": "personnel",
    "stagiaires": "stagiaire",
    "travaux": "travail",
    "inclusions": "inclusion",

    "produits": "produit",
    "clients": "client",
    "clienteles": "clientele",
    "ventes": "vente",
    "vehicules": "vehicule",
    "agences": "agence",
    "marches": "marche",
    "prospects": "prospect",
    "commandes": "commande",
    "portefeuilles": "portefeuille",

    "clauses": "clause",
    "contrats": "contrat",
    "droits": "droit",
    "codes": "code",
    "fraudes": "fraude",
    "corruptions": "corruption",
    "litiges": "litige",
    "reglementations": "reglementation",
    "legislations": "legislation",
    "sanctions": "sanction",

    "strategies": "strategie",
    "orientations": "orientation",
    "visions": "vision",
    "missions": "mission",
    "ambitions": "ambition",
    "perspectives": "perspective",
    "gouvernances": "gouvernance",
    "administrateurs": "administrateur",

    "donnees": "donnee",
    "applications": "application",
    "logiciels": "logiciel",
    "systemes": "systeme",
    "reseaux": "reseau",
    "technologies": "technologie",

    "marques": "marque",
    "communications": "communication",
    "campagnes": "campagne",
    "audiences": "audience",
    "reputations": "reputation",
}

ALIASES_MULTI = {
    "securite des systemes d information": "securite des systemes d information",
    "systemes d information": "systeme d information",
    "donnees personnelles": "donnee personnelle",
    "etats financiers": "etat financier",
    "comptes annuels": "compte annuel",
}


# ============================================================================
# VOCABULAIRE GLOBAL
# ============================================================================

VOCAB = {
    "direction": {
        "forts": DIRECTION_FORTS,
        "contextuels": DIRECTION_CONTEXTUELS,
        "repetition": DIRECTION_REPETITION,
    },
    "finance": {
        "forts": FINANCE_FORTS,
        "contextuels": FINANCE_CONTEXTUELS,
        "repetition": FINANCE_REPETITION,
    },
    "it": {
        "forts": IT_FORTS,
        "contextuels": IT_CONTEXTUELS,
        "repetition": IT_REPETITION,
    },
    "rh": {
        "forts": RH_FORTS,
        "contextuels": RH_CONTEXTUELS,
        "repetition": RH_REPETITION,
    },
    "commerce": {
        "forts": COMMERCE_FORTS,
        "contextuels": COMMERCE_CONTEXTUELS,
        "repetition": COMMERCE_REPETITION,
    },
    "juridique": {
        "forts": JURIDIQUE_FORTS,
        "contextuels": JURIDIQUE_CONTEXTUELS,
        "repetition": JURIDIQUE_REPETITION,
    },
    "marketing": {
        "forts": MARKETING_FORTS,
        "contextuels": MARKETING_CONTEXTUELS,
        "repetition": MARKETING_REPETITION,
    },
}


# ============================================================================
# UTILITAIRES TEXTE
# ============================================================================

def normaliser_texte(text: Any) -> str:
    if text is None:
        return ""

    text = str(text)

    text = (
        text
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u00a0", " ")
    )

    text = unicodedata.normalize("NFKD", text)

    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = text.lower()

    text = re.sub(r"[-_/]", " ", text)

    text = text.replace("'", " ")

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def mot_ou_expression_regex(term: str) -> str:
    term = normaliser_texte(term)

    if not term:
        return ""

    mots = term.split()
    result = []

    for mot in mots:
        if len(mot) >= 4:
            if mot.endswith("s"):
                piece = re.escape(mot)
            else:
                piece = re.escape(mot) + r"s?"
        else:
            piece = re.escape(mot)

        result.append(piece)

    return r"\b" + r"\s+".join(result) + r"\b"


def extraire_texte(chunk: Dict[str, Any]) -> str:
    champs = [
        "text",
        "texte",
        "content",
        "page_content",
        "chunk",
        "contenu",
    ]

    morceaux = []

    for champ in champs:
        valeur = chunk.get(champ)

        if valeur:
            morceaux.append(str(valeur))

    metadata = chunk.get("metadata")

    if isinstance(metadata, dict):
        for champ in champs:
            valeur = metadata.get(champ)

            if valeur:
                morceaux.append(str(valeur))

    return "\n".join(morceaux)


def get_field(
    chunk: Dict[str, Any],
    field: str,
    default: Any = None,
) -> Any:

    if field in chunk:
        return chunk.get(field)

    metadata = chunk.get("metadata")

    if isinstance(metadata, dict) and field in metadata:
        return metadata.get(field)

    return default


def set_field(
    chunk: Dict[str, Any],
    field: str,
    value: Any,
) -> None:
    chunk[field] = value


def canonicaliser_phrase(term: str) -> str:
    term = normaliser_texte(term)

    if not term:
        return ""

    if term in ALIASES_MULTI:
        return ALIASES_MULTI[term]

    return ALIASES.get(term, term)


def remplacer_aliases_dans_texte(text: str) -> str:
    """
    Normalisation canonique en deux étapes :
    1) expressions multi-mots les plus longues ;
    2) alias unitaires ;
    3) expressions multi-mots une seconde fois pour traiter les
       formes produites par les alias unitaires.
    """
    text = normaliser_texte(text)

    if not text:
        return ""

    # Les expressions longues doivent être traitées avant leurs sous-chaînes.
    for source, cible in sorted(
        ALIASES_MULTI.items(),
        key=lambda x: len(x[0]),
        reverse=True,
    ):
        pattern = mot_ou_expression_regex(source)
        if pattern:
            text = re.sub(pattern, cible, text)

    # Alias unitaires.
    mots = text.split()
    mots = [ALIASES.get(mot, mot) for mot in mots]
    text = " ".join(mots)

    # Deuxième passage : utile pour "etats financiers" -> "etat financier"
    # et les expressions dont la forme canonique contient des mots aliasés.
    for source, cible in sorted(
        ALIASES_MULTI.items(),
        key=lambda x: len(x[0]),
        reverse=True,
    ):
        pattern = mot_ou_expression_regex(source)
        if pattern:
            text = re.sub(pattern, cible, text)

    return text


def compter_occurrences(
    text: str,
    terme: str,
) -> int:

    pattern = mot_ou_expression_regex(terme)

    if not pattern:
        return 0

    return len(
        re.findall(
            pattern,
            text,
        )
    )


def compter_occurrences_hors_exclusion(
    text: str,
    terme: str,
    exclusions: set,
) -> int:
    """
    CORRECTIF #1
    ------------
    Compte les occurrences de `terme` qui ne sont PAS rattachées à une
    expression exclue contenant ce terme (ex: terme="bilan",
    exclusions contient "bilan carbone" -> on retire uniquement les
    occurrences de "bilan carbone", pas toutes les occurrences de
    "bilan").

    Avant ce correctif, la présence de "bilan carbone" n'importe où
    dans le chunk faisait disparaître TOUTES les occurrences de
    "bilan", y compris celles liées à un vrai bilan comptable ailleurs
    dans le même chunk (cf. Wafa_Assurance page 114 dans le dry-run
    v9 : score=6 sur bilan=3, mais rejeté à tort).
    """

    total = compter_occurrences(text, terme)

    exclues = 0

    for expression in exclusions:

        mots_expression = expression.split()

        if terme in mots_expression:
            exclues += compter_occurrences(text, expression)

    return max(0, total - exclues)


def construire_compteurs(
    text: str,
    termes: set,
) -> Counter:

    counter = Counter()

    for terme in termes:
        n = compter_occurrences(
            text,
            terme,
        )

        if n > 0:
            counter[terme] = n

    return counter


def nombre_mots(text: str) -> int:
    if not text:
        return 0

    return len(text.split())


# ============================================================================
# DETECTION SOMMAIRE / INDEX
# ============================================================================

def est_sommaire_ou_index(raw_text: str) -> bool:

    text = normaliser_texte(raw_text)

    if not text:
        return False

    lignes = [
        ligne.strip()
        for ligne in raw_text.splitlines()
        if ligne.strip()
    ]

    mots = text.split()

    if not lignes:
        return False

    premiers_mots = " ".join(
        mots[:100]
    )

    titres = {
        "sommaire",
        "table des matieres",
        "table matieres",
        "tableau des matieres",
        "contents",
        "index",
    }

    titre_detecte = any(
        re.search(
            rf"\\b{re.escape(titre)}\\b",
            premiers_mots,
        )
        for titre in titres
    )

    if titre_detecte and len(lignes) >= 5:
        return True

    # Détection table des matières
    if len(lignes) >= 8 and len(mots) <= 800:

        lignes_toc = 0

        for ligne in lignes:
            ligne_norm = normaliser_texte(ligne)

            if not ligne_norm:
                continue

            if (
                re.search(r"\.{2,}\s*\d+$", ligne)
                or re.search(r"\s\d+$", ligne)
                or re.search(r"\bpage\s+\d+\b", ligne_norm)
            ):
                lignes_toc += 1

        ratio = lignes_toc / len(lignes)

        if ratio >= 0.75:
            return True

    # Détection index lexical compact
    if (
        len(mots) <= 250
        and len(lignes) >= 8
    ):
        courtes = sum(
            1
            for ligne in lignes
            if len(normaliser_texte(ligne).split()) <= 6
        )

        ratio_courtes = courtes / len(lignes)

        if ratio_courtes >= 0.85:
            return True

    return False


# ============================================================================
# EXCLUSIONS
# ============================================================================

def contient_terme(
    text: str,
    terme: str,
) -> bool:
    return compter_occurrences(
        text,
        terme,
    ) > 0


def finance_exclue(text: str) -> bool:
    """Conservée pour compat / diagnostics, mais n'est plus utilisée
    pour effacer tout le score 'bilan' (voir CORRECTIF #1)."""
    return any(
        contient_terme(text, terme)
        for terme in FINANCE_EXCLUSIONS
    )


def finance_macro_exclue(text: str) -> bool:
    return any(
        contient_terme(text, terme)
        for terme in FINANCE_MACRO_EXCLUSIONS
    )


def rh_exclue(text: str) -> bool:
    return any(
        contient_terme(text, terme)
        for terme in RH_EXCLUSIONS
    )


# ============================================================================
# ANALYSE D'UN DEPARTEMENT
# ============================================================================

def analyser_departement(
    dept: str,
    text: str,
) -> Dict[str, Any]:

    config = VOCAB[dept]

    forts = construire_compteurs(
        text,
        config["forts"],
    )

    contextuels = construire_compteurs(
        text,
        config["contextuels"],
    )

    termes = Counter()

    termes.update(forts)
    termes.update(contextuels)

    score = (
        2 * sum(forts.values())
        + sum(contextuels.values())
    )

    return {
        "departement": dept,
        "score": score,
        "forts": forts,
        "contextuels": contextuels,
        "termes": termes,
        "nb_termes_distincts": len(termes),
        "nb_forts": len(forts),
    }


# ============================================================================
# OUTILS VALIDATION
# ============================================================================

def has_pair(
    counter: Counter,
    pairs: set,
) -> bool:

    presentes = {
        terme
        for terme, count in counter.items()
        if count > 0
    }

    for pair in pairs:
        if pair.issubset(presentes):
            return True

    return False


# ============================================================================
# VALIDATION DIRECTION
# ============================================================================

def validation_direction(
    info: Dict[str, Any],
    text: str,
) -> Tuple[bool, str]:

    forts = info["forts"]
    context = info["contextuels"]
    score = info["score"]

    if forts:
        return True, "fort"

    for terme, seuil in DIRECTION_REPETITION.items():

        if context.get(terme, 0) >= seuil:
            return True, "repetition_direction"

    presentes = set(context.keys())

    if (
        "strategie" in presentes
        and (
            "ambition" in presentes
            or "vision" in presentes
            or "perspective" in presentes
        )
    ):
        return True, "strategie_ambition"

    if (
        "strategique" in presentes
        and (
            "ambition" in presentes
            or "vision" in presentes
            or "perspective" in presentes
        )
    ):
        return True, "strategique_ambition"

    if (
        "gouvernance" in presentes
        and (
            "strategie" in presentes
            or "strategique" in presentes
        )
    ):
        return True, "gouvernance_strategie"

    if (
        len(presentes) >= 2
        and score >= 4
    ):
        if (
            "mission" in presentes
            or "vision" in presentes
            or "gouvernance" in presentes
        ):
            return True, "contexte_direction"

    return False, ""


# ============================================================================
# VALIDATION FINANCE
# ============================================================================

def validation_finance(
    info: Dict[str, Any],
    text: str,
) -> Tuple[bool, str]:

    forts = info["forts"].copy()
    context = info["contextuels"]
    score = info["score"]

    # ------------------------------------------------------------------
    # CORRECTIF #1 : exclusion ciblée sur "bilan" uniquement, en ne
    # retirant que les occurrences réellement rattachées à une
    # expression exclue (ex: "bilan carbone"), pas tout le terme.
    # ------------------------------------------------------------------
    if "bilan" in forts:

        net = compter_occurrences_hors_exclusion(
            text,
            "bilan",
            FINANCE_EXCLUSIONS,
        )

        if net <= 0:
            forts.pop("bilan", None)
        else:
            forts["bilan"] = net

    if forts:
        return True, "fort"

    # ------------------------------------------------------------------
    # CORRECTIF #2 : finance_macro_exclue() est maintenant branchée.
    # Un chunk purement macro-économique (pib, inflation, banque
    # centrale...) sans aucun terme "fort" finance n'est pas classé
    # finance sur la seule base de termes contextuels.
    # ------------------------------------------------------------------
    if finance_macro_exclue(text):
        return False, ""

    for terme, seuil in FINANCE_REPETITION.items():

        if context.get(terme, 0) >= seuil:
            return True, "repetition_finance"

    if has_pair(
        context,
        {
            frozenset({"comptable", "financier"}),
            frozenset({"resultat", "exercice"}),
            frozenset({"dette", "financier"}),
            frozenset({"compte", "financier"}),
            frozenset({"compte", "exercice"}),
            frozenset({"exercice", "perte"}),
            *FINANCE_PAIRS,
        },
    ):
        return True, "paire_finance"

    presentes = set(context.keys())

    if (
        len(presentes) >= 2
        and score >= 4
        and (
            "resultat" in presentes
            or "compte" in presentes
            or "comptable" in presentes
            or "dette" in presentes
            or "financier" in presentes
            or "placement" in presentes
            or "technique" in presentes
            or "prime" in presentes
            or "sinistre" in presentes
        )
    ):
        return True, "contexte_finance"

    return False, ""


# ============================================================================
# VALIDATION IT
# ============================================================================

def validation_it(
    info: Dict[str, Any],
    text: str,
) -> Tuple[bool, str]:

    forts = info["forts"]
    context = info["contextuels"]
    score = info["score"]

    if forts:
        return True, "fort"

    for terme, seuil in IT_REPETITION.items():

        if context.get(terme, 0) >= seuil:
            return True, "repetition_it"

    presents_discriminants = {
        terme
        for terme in IT_DISCRIMINANTS
        if context.get(terme, 0) > 0
    }

    if len(presents_discriminants) >= 2:
        return True, "discriminants_it"

    if (
        context.get("systeme", 0) > 0
        and context.get("informatique", 0) > 0
    ):
        return True, "systeme_informatique"

    # ------------------------------------------------------------------
    # CORRECTIF #3 : fallback "contexte_it", symétrique à ce qui existe
    # déjà pour direction/finance/rh. Un chunk avec un score IT correct
    # (>=3) et au moins un terme discriminant IT réel passe désormais,
    # au lieu d'être rejeté faute de 2ème terme discriminant distinct.
    # ------------------------------------------------------------------
    if (
        score >= 3
        and presents_discriminants
    ):
        return True, "contexte_it"

    return False, ""


# ============================================================================
# VALIDATION RH
# ============================================================================

def validation_rh(
    info: Dict[str, Any],
    text: str,
) -> Tuple[bool, str]:

    forts = info["forts"]
    context = info["contextuels"]
    score = info["score"]

    if forts:
        return True, "fort"

    if rh_exclue(text):

        exceptions = {
            "formation",
            "collaborateur",
            "ressources humaines",
            "effectif",
            "recrutement",
        }

        if not any(
            context.get(terme, 0) > 0
            for terme in exceptions
        ):
            return False, ""

    if has_pair(
        context,
        RH_PAIRS,
    ):
        return True, "paire_rh"

    for terme, seuil in RH_REPETITION.items():

        if context.get(terme, 0) >= seuil:
            return True, "repetition_rh"

    if (
        len(context) >= 2
        and score >= 3
    ):
        return True, "contexte_rh"

    return False, ""


# ============================================================================
# VALIDATION COMMERCE
# ============================================================================

def validation_commerce(
    info: Dict[str, Any],
    text: str,
) -> Tuple[bool, str]:

    forts = info["forts"]
    context = info["contextuels"]
    score = info["score"]

    if forts:
        return True, "fort"

    if has_pair(
        context,
        COMMERCE_PAIRS,
    ):
        return True, "paire_commerce"

    for terme, seuil in COMMERCE_REPETITION.items():

        if context.get(terme, 0) >= seuil:
            return True, "repetition_commerce"

    if (
        context.get("produit", 0) > 0
        and context.get("marche", 0) > 0
    ):
        return True, "produit_marche"

    # ------------------------------------------------------------------
    # CORRECTIF #3 : fallback "contexte_commerce". Auparavant un chunk
    # avec uniquement "produit" ou "marche" répété (sans atteindre le
    # seuil de répétition et sans les deux ensemble) était rejeté,
    # même avec un score correct et 2+ termes contextuels distincts.
    # ------------------------------------------------------------------
    if (
        len(context) >= 2
        and score >= 4
    ):
        return True, "contexte_commerce"

    return False, ""


# ============================================================================
# VALIDATION JURIDIQUE
# ============================================================================

def validation_juridique(
    info: Dict[str, Any],
    text: str,
) -> Tuple[bool, str]:

    forts = info["forts"]
    context = info["contextuels"]

    if forts:
        return True, "fort"

    for terme, seuil in JURIDIQUE_REPETITION.items():

        if context.get(terme, 0) >= seuil:
            return True, "repetition_juridique"

    if has_pair(
        context,
        JURIDIQUE_PAIRS,
    ):
        return True, "paire_juridique"

    if context.get("contrat", 0) >= 4:
        return True, "repetition_contrat"

    if (
        context.get("contrat", 0) > 0
        and context.get("droit", 0) > 0
    ):
        return True, "contrat_droit"

    # Documents réglementaires/juridiques sans mot "contrat".
    signaux_reglementaires = {
        "loi",
        "projet de loi",
        "dahir",
        "code des assurances",
        "code de la route",
        "indemnisation",
        "victime",
    }
    nb_signaux_reglementaires = sum(
        1
        for terme in signaux_reglementaires
        if context.get(terme, 0) > 0
    )

    if nb_signaux_reglementaires >= 2:
        return True, "contexte_reglementaire_juridique"

    return False, ""


# ============================================================================
# VALIDATION MARKETING
# ============================================================================

def validation_marketing(
    info: Dict[str, Any],
    text: str,
) -> Tuple[bool, str]:

    forts = info["forts"]
    context = info["contextuels"]
    score = info["score"]

    if forts:
        return True, "fort"

    if has_pair(
        context,
        MARKETING_PAIRS,
    ):
        return True, "paire_marketing"

    for terme, seuil in MARKETING_REPETITION.items():

        count = context.get(
            terme,
            0,
        )

        if count >= seuil:

            # communication seule ne suffit pas
            if terme == "communication":

                if not any(
                    context.get(x, 0) > 0
                    for x in {
                        "marque",
                        "campagne",
                        "audience",
                        "reputation",
                    }
                ):
                    continue

            return True, "repetition_marketing"

    # ------------------------------------------------------------------
    # CORRECTIF #3 : fallback "contexte_marketing". Un terme marketing
    # contextuel (hors "communication" seule, toujours exclue ici)
    # répété au moins 2 fois suffit désormais à qualifier le chunk.
    # ------------------------------------------------------------------
    for terme in ("campagne", "marque", "reputation", "positionnement"):

        if context.get(terme, 0) >= 2:
            return True, "contexte_marketing"

    return False, ""


# ============================================================================
# VALIDATORS
# ============================================================================

VALIDATORS = {
    "direction": validation_direction,
    "finance": validation_finance,
    "it": validation_it,
    "rh": validation_rh,
    "commerce": validation_commerce,
    "juridique": validation_juridique,
    "marketing": validation_marketing,
}


# ============================================================================
# CLASSIFICATION D'UN CHUNK
# ============================================================================

def classifier_chunk(
    chunk: Dict[str, Any],
) -> Dict[str, Any]:

    raw_text = extraire_texte(chunk)

    if not raw_text:

        return {
            "classification": None,
            "scores": {},
            "details": {},
            "raison": "texte_vide",
            "limite": False,
            "texte": "",
        }

    if est_sommaire_ou_index(raw_text):

        return {
            "classification": None,
            "scores": {},
            "details": {},
            "raison": "sommaire_ou_index",
            "limite": False,
            "texte": "",
        }

    text = normaliser_texte(raw_text)

    text = remplacer_aliases_dans_texte(text)

    scores = {}
    details = {}
    candidats = []

    # ------------------------------------------------------------------------
    # ANALYSE DE CHAQUE DEPARTEMENT
    # ------------------------------------------------------------------------

    for dept in DEPARTEMENTS:

        info = analyser_departement(
            dept,
            text,
        )

        # Correction robuste :
        # tous les validators doivent respecter la même signature
        # (info, text).
        validator = VALIDATORS.get(dept)

        if validator is None:
            raise RuntimeError(
                f"Validator introuvable pour le département : {dept}"
            )

        valide, raison = validator(
            info,
            text,
        )

        scores[dept] = info["score"]

        # IMPORTANT :
        # nb_forts doit être conservé ici car le tri des candidats
        # l'utilise ensuite.
        details[dept] = {
            "score": info["score"],
            "forts": info["forts"],
            "contextuels": info["contextuels"],
            "termes": info["termes"],
            "nb_termes_distincts": info[
                "nb_termes_distincts"
            ],
            "nb_forts": info["nb_forts"],
            "raison": raison,
            "valide": valide,
        }

        if valide:
            candidats.append(dept)

    # ------------------------------------------------------------------------
    # AUCUN DEPARTEMENT
    # ------------------------------------------------------------------------

    if not candidats:

        return {
            "classification": None,
            "scores": scores,
            "details": details,
            "raison": "aucun_departement",
            "limite": False,
            "texte": text,
        }

    # ------------------------------------------------------------------------
    # TRI DES CANDIDATS
    # ------------------------------------------------------------------------

    candidats = sorted(
        candidats,
        key=lambda d: (
            details[d]["score"],
            details[d]["nb_forts"],
            details[d]["nb_termes_distincts"],
        ),
        reverse=True,
    )

    primary = candidats[0]

    selected = [
        primary
    ]

    # ------------------------------------------------------------------------
    # SECOND DEPARTEMENT
    # ------------------------------------------------------------------------

    if len(candidats) > 1:

        secondary = candidats[1]

        score_primary = details[primary]["score"]
        score_secondary = details[secondary]["score"]

        ratio = (
            score_secondary / score_primary
            if score_primary > 0
            else 0
        )

        secondary_forts = details[secondary][
            "nb_forts"
        ]

        secondary_terms = details[secondary][
            "nb_termes_distincts"
        ]

        independent_proof = (
            secondary_forts >= 1
            or secondary_terms >= 2
        )

        eligible_secondary = (
            score_secondary >= SEUIL_SECOND_DEPT
            and score_primary > 0
            and ratio >= RATIO_SECOND_DEPT
            and independent_proof
        )

        # Marketing strict
        if secondary == "marketing":

            raison_secondary = details[
                secondary
            ]["raison"]

            if raison_secondary not in {
                "fort",
                "paire_marketing",
                "repetition_marketing",
                "contexte_marketing",
            }:
                eligible_secondary = False

        # Direction secondaire : preuve forte ou répétition
        if secondary == "direction":

            raison_secondary = details[
                secondary
            ]["raison"]

            if raison_secondary not in {
                "fort",
                "repetition_direction",
                "strategie_ambition",
                "strategique_ambition",
                "gouvernance_strategie",
            }:
                eligible_secondary = False

        # Finance / RH sans fort :
        # il faut au moins 2 termes distincts.
        if secondary in {
            "finance",
            "rh",
        }:

            if secondary_forts == 0 and secondary_terms < 2:
                eligible_secondary = False

        if eligible_secondary:

            selected.append(
                secondary
            )

    # Sécurité : maximum 2 départements.
    selected = selected[:MAX_DEPTS]

    # ------------------------------------------------------------------------
    # CAS LIMITE
    # ------------------------------------------------------------------------

    limite = False

    if len(selected) > 1:
        limite = True

    elif details[primary]["score"] <= 4:
        limite = True

    elif details[primary]["nb_forts"] == 0:
        limite = True

    # ------------------------------------------------------------------------
    # RESULTAT
    # ------------------------------------------------------------------------

    return {
        "classification": selected,
        "scores": scores,
        "details": details,
        "raison": "classe",
        "limite": limite,
        "texte": text,
    }


# ============================================================================
# IDENTIFIANTS DEBUG
# ============================================================================

def obtenir_id_document(
    chunk: Dict[str, Any],
) -> str:

    champs = [
        "entreprise",
        "company",
        "societe",
        "source",
        "nom_entreprise",
    ]

    for champ in champs:

        valeur = get_field(
            chunk,
            champ,
            "",
        )

        if valeur:
            return str(valeur)

    return "entreprise_inconnue"


def obtenir_page(
    chunk: Dict[str, Any],
) -> str:

    champs = [
        "page",
        "page_number",
        "numero_page",
        "page_num",
    ]

    for champ in champs:

        valeur = get_field(
            chunk,
            champ,
            "",
        )

        if valeur is not None and str(valeur).strip():
            return str(valeur)

    return "?"


# ============================================================================
# AFFICHAGE DETAILS
# ============================================================================

def afficher_details(
    chunk: Dict[str, Any],
    resultat: Dict[str, Any],
) -> None:

    entreprise = obtenir_id_document(
        chunk
    )

    page = obtenir_page(
        chunk
    )

    print(
        f"\nEntreprise : {entreprise}"
    )

    print(
        f"Page       : {page}"
    )

    classification = resultat.get(
        "classification"
    )

    if classification:

        print(
            "Départements : "
            + ", ".join(classification)
        )

        details = resultat.get(
            "details",
            {},
        )

        for dept in classification:

            info = details.get(
                dept,
                {},
            )

            print(
                f"  - {dept} : "
                f"score={info.get('score', 0)} "
                f"raison={info.get('raison', '')} "
                f"forts={dict(info.get('forts', {}))} "
                f"termes={dict(info.get('termes', {}))}"
            )

    else:

        print(
            "Département : NON CLASSÉ"
        )

        print(
            "Raison       : "
            + str(
                resultat.get(
                    "raison",
                    "",
                )
            )
        )

        scores = resultat.get(
            "scores",
            {},
        )

        if scores:

            best = max(
                scores,
                key=scores.get,
            )

            print(
                f"Meilleur score : {best} "
                f"({scores[best]})"
            )

            info = resultat.get(
                "details",
                {},
            ).get(
                best,
                {},
            )

            print(
                "Termes : "
                + str(
                    dict(
                        info.get(
                            "termes",
                            {},
                        )
                    )
                )
            )


# ============================================================================
# ANALYSE METADATA
# ============================================================================

def analyser_metadata(
    data: List[Dict[str, Any]],
    limite_max: int = 50,
    nonclasses_max: int = 50,
) -> Dict[str, Any]:

    stats = {
        "total": 0,
        "departements": Counter(),
        "nonclasses": 0,
        "multi": 0,
    }

    resultats = []

    total_entreprise = 0
    total_public = 0
    total_traite = 0
    total_sommaires = 0

    # ------------------------------------------------------------------------
    # PARCOURS DES CHUNKS
    # ------------------------------------------------------------------------

    for chunk in data:

        stats["total"] += 1

        type_document = get_field(
            chunk,
            "type_document",
            None,
        )

        # IMPORTANT :
        # seuls les chunks entreprise sont classifiés.
        if type_document != "entreprise":

            total_public += 1
            continue

        total_entreprise += 1

        resultat = classifier_chunk(
            chunk
        )

        # Sommaire / index ignoré
        if resultat["raison"] == "sommaire_ou_index":

            total_sommaires += 1

            resultats.append(
                (chunk, resultat)
            )

            continue

        total_traite += 1

        classification = resultat.get(
            "classification"
        )

        if classification:

            for dept in classification:
                stats["departements"][dept] += 1

            if len(classification) > 1:
                stats["multi"] += 1

        else:
            stats["nonclasses"] += 1

        resultats.append(
            (chunk, resultat)
        )

    # ------------------------------------------------------------------------
    # AFFICHAGE GLOBAL
    # ------------------------------------------------------------------------

    print()
    print(
        f"Chunks entreprise       : {total_entreprise}"
    )

    print(
        f"Chunks public_reglementaire : {total_public}"
    )

    print(
        f"Chunks entreprise traités : {total_traite}"
    )

    print(
        f"Sommaires / index ignorés : {total_sommaires}"
    )

    print()
    print(
        "Répartition par département :"
    )

    for dept in DEPARTEMENTS:

        count = stats[
            "departements"
        ][dept]

        print(
            f"   {dept:12s}: {count}"
        )

    # ------------------------------------------------------------------------
    # MONO / MULTI / NON CLASSES
    # ------------------------------------------------------------------------

    mono = 0
    multi = 0
    nonclasses = 0
    total_depts = 0

    for chunk, resultat in resultats:

        if resultat["raison"] == "sommaire_ou_index":
            continue

        classification = resultat.get(
            "classification"
        )

        if not classification:

            nonclasses += 1
            continue

        total_depts += len(
            classification
        )

        if len(classification) == 1:
            mono += 1
        else:
            multi += 1

    print()
    print(
        f"Mono-département : {mono}"
    )

    print(
        f"Multi-département : {multi}"
    )

    print(
        f"Non classés       : {nonclasses}"
    )

    print(
        f"Total affectations : {total_depts}"
    )

    # ------------------------------------------------------------------------
    # CAS LIMITES
    # ------------------------------------------------------------------------

    limites = [
        (
            chunk,
            resultat,
        )
        for chunk, resultat in resultats
        if resultat.get("limite")
    ]

    limites = sorted(
        limites,
        key=lambda item: (
            len(
                item[1].get(
                    "classification"
                ) or []
            ),
            -max(
                item[1].get(
                    "scores",
                    {"x": 0},
                ).values()
                or [0]
            ),
        ),
        reverse=True,
    )

    print()
    print(
        f"CAS LIMITES : {len(limites)}"
    )

    if limites and limite_max > 0:

        print(
            f"Affichage des {min(limite_max, len(limites))} premiers :"
        )

        for chunk, resultat in limites[:limite_max]:

            afficher_details(
                chunk,
                resultat,
            )

    # ------------------------------------------------------------------------
    # NON CLASSES
    # ------------------------------------------------------------------------

    nonclasses_list = [
        (
            chunk,
            resultat,
        )
        for chunk, resultat in resultats
        if (
            resultat.get("classification") is None
            and resultat.get("raison")
            not in {
                "sommaire_ou_index",
                "texte_vide",
            }
        )
    ]

    def score_max(
        item: Tuple[
            Dict[str, Any],
            Dict[str, Any],
        ],
    ) -> float:

        scores = item[1].get(
            "scores",
            {},
        )

        if not scores:
            return 0

        return max(
            scores.values()
        )

    nonclasses_list = sorted(
        nonclasses_list,
        key=score_max,
        reverse=True,
    )

    return {
        "resultats": resultats,
        "stats": stats,
        "totals": {
            "total": stats["total"],
            "entreprise": total_entreprise,
            "public": total_public,
            "traite": total_traite,
            "sommaires": total_sommaires,
            "mono": mono,
            "multi": multi,
            "nonclasses": nonclasses,
            "total_depts": total_depts,
        },
        "nonclasses_list": nonclasses_list[
            :nonclasses_max
        ],
        "limites": limites,
        "nonclasses_max": nonclasses_max,
    }


# ============================================================================
# CHAMPS MODIFIABLES
# ============================================================================

CHAMPS_CLASSIFIER = {
    "departements",
    "departements_source",
    "departements_termes",
}


def nettoyer_anciens_champs_classifier(
    chunk: Dict[str, Any],
) -> None:
    """
    Supprime uniquement les champs produits par ce classifier (ou une
    version précédente du même classifier). Les autres métadonnées restent
    intactes.
    """
    source = chunk.get("departements_source")

    appartient_au_classifier = (
        isinstance(source, str)
        and source.startswith("classifier_v")
    )

    if not appartient_au_classifier:
        return

    for champ in CHAMPS_CLASSIFIER:
        chunk.pop(champ, None)


# ============================================================================
# APPLICATION DES RESULTATS
# ============================================================================

def appliquer(
    data: List[Dict[str, Any]],
    resultats: List[
        Tuple[
            Dict[str, Any],
            Dict[str, Any],
        ]
    ],
) -> Dict[str, int]:

    modifies = 0
    nettoyes = 0

    for chunk, resultat in resultats:

        type_document = get_field(
            chunk,
            "type_document",
            None,
        )

        # Sécurité absolue :
        # ne jamais toucher aux non-entreprise.
        if type_document != "entreprise":
            continue

        classification = resultat.get(
            "classification"
        )

        raison = resultat.get(
            "raison"
        )

        # --------------------------------------------------------------------
        # SOMMAIRE / INDEX
        # --------------------------------------------------------------------

        if raison == "sommaire_ou_index":

            avant = any(
                champ in chunk
                for champ in CHAMPS_CLASSIFIER
            )

            nettoyer_anciens_champs_classifier(
                chunk
            )

            if avant:
                nettoyes += 1

            continue

        # --------------------------------------------------------------------
        # NON CLASSE
        # --------------------------------------------------------------------

        if not classification:

            avant = any(
                champ in chunk
                for champ in CHAMPS_CLASSIFIER
            )

            nettoyer_anciens_champs_classifier(
                chunk
            )

            if avant:
                nettoyes += 1

            continue

        # --------------------------------------------------------------------
        # CONSTRUCTION DES TERMES
        # --------------------------------------------------------------------

        termes_par_dept = {}

        details = resultat.get(
            "details",
            {},
        )

        for dept in classification:

            info = details.get(
                dept,
                {},
            )

            termes = info.get(
                "termes",
                {},
            )

            termes_tries = sorted(
                termes.items(),
                key=lambda x: (
                    -x[1],
                    x[0],
                ),
            )

            termes_par_dept[dept] = [
                terme
                for terme, count
                in termes_tries
            ]

        # --------------------------------------------------------------------
        # NETTOYAGE
        # --------------------------------------------------------------------

        nettoyer_anciens_champs_classifier(
            chunk
        )

        # --------------------------------------------------------------------
        # ECRITURE UNIQUEMENT DES 3 CHAMPS
        # --------------------------------------------------------------------

        set_field(
            chunk,
            "departements",
            classification,
        )

        set_field(
            chunk,
            "departements_source",
            SOURCE_TAG,
        )

        set_field(
            chunk,
            "departements_termes",
            termes_par_dept,
        )

        modifies += 1

    return {
        "modifies": modifies,
        "nettoyes": nettoyes,
    }


# ============================================================================
# SAUVEGARDE
# ============================================================================

def sauvegarder(
    data: List[Dict[str, Any]],
    metadata_path: Path,
) -> Path:

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_path = metadata_path.with_name(
        f"{metadata_path.stem}.json.backup_{timestamp}"
    )

    shutil.copy2(
        metadata_path,
        backup_path,
    )

    temp_path = metadata_path.with_suffix(
        ".json.tmp"
    )

    with open(
        temp_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(
        temp_path,
        metadata_path,
    )

    return backup_path


# ============================================================================
# RESOLUTION DU CHEMIN METADATA
# ============================================================================

def resoudre_metadata_path(explicit: Optional[str] = None) -> Path:
    """
    Résout le chemin réel de metadata.json.

    Le chemin attendu du projet est :
        backend/data/index/metadata.json

    --metadata permet de forcer un autre chemin sans modifier le code.
    """
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"metadata.json introuvable via --metadata : {path}"
            )
        return path

    candidats = [
        DEFAULT_METADATA_PATH,
        BASE_DIR / "metadata.json",
        BASE_DIR.parent / "metadata.json",
        BASE_DIR.parent / "backend" / "data" / "index" / "metadata.json",
    ]

    vus = set()
    for path in candidats:
        path = path.resolve()
        if path in vus:
            continue
        vus.add(path)
        if path.exists():
            return path

    # Dernier recours : recherche limitée au dossier du projet.
    racine = BASE_DIR.parent
    trouves = sorted(
        p.resolve()
        for p in racine.rglob("metadata.json")
        if p.is_file()
    )

    if len(trouves) == 1:
        return trouves[0]

    if len(trouves) > 1:
        details = "\n".join(f"  - {p}" for p in trouves)
        raise FileNotFoundError(
            "Plusieurs metadata.json ont été trouvés. "
            "Utilisez --metadata avec le bon fichier :\n"
            + details
        )

    raise FileNotFoundError(
        "metadata.json introuvable. Chemin attendu : "
        f"{DEFAULT_METADATA_PATH}\n"
        'Vous pouvez préciser : --metadata "C:\\chemin\\metadata.json"'
    )


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Classifier les chunks entreprise "
            "par département."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Appliquer les classifications "
            "dans metadata.json"
        ),
    )

    parser.add_argument(
        "--metadata",
        type=str,
        default=None,
        help=(
            "Chemin explicite vers metadata.json. "
            "Par défaut : backend/data/index/metadata.json"
        ),
    )

    parser.add_argument(
        "--show-limite",
        type=int,
        default=50,
        help=(
            "Nombre maximum de cas limites "
            "à afficher."
        ),
    )

    parser.add_argument(
        "--show-non-classes",
        type=int,
        default=50,
        help=(
            "Nombre maximum de chunks non classés "
            "à afficher."
        ),
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------------
    # CHARGEMENT
    # ------------------------------------------------------------------------

    metadata_path = resoudre_metadata_path(
        args.metadata
    )

    print(
        "Chargement de l'index metadata..."
    )
    print(
        f"Fichier : {metadata_path}"
    )

    with open(
        metadata_path,
        "r",
        encoding="utf-8",
    ) as f:

        data = json.load(f)

    if not isinstance(data, list):

        raise ValueError(
            "metadata.json doit contenir "
            "une liste de chunks."
        )

    print(
        f"{len(data)} chunks disponibles."
    )

    # ------------------------------------------------------------------------
    # ANALYSE
    # ------------------------------------------------------------------------

    analyse = analyser_metadata(
        data,
        limite_max=max(0, args.show_limite),
        nonclasses_max=max(0, args.show_non_classes),
    )

    # ------------------------------------------------------------------------
    # AFFICHAGE NON CLASSES
    # ------------------------------------------------------------------------

    if args.show_non_classes:

        nonclasses_list = analyse[
            "nonclasses_list"
        ]

        print()
        print(
            "============================================================"
        )
        print(
            "CHUNKS NON CLASSES"
        )
        print(
            "============================================================"
        )

        if not nonclasses_list:

            print(
                "Aucun chunk non classé."
            )

        else:

            for chunk, resultat in nonclasses_list[
                :args.show_non_classes
            ]:

                afficher_details(
                    chunk,
                    resultat,
                )

    # ------------------------------------------------------------------------
    # MODE APPLY
    # ------------------------------------------------------------------------

    if args.apply:

        print()
        print(
            "============================================================"
        )
        print(
            "MODE APPLY"
        )
        print(
            "============================================================"
        )

        application = appliquer(
            data,
            analyse["resultats"],
        )

        backup_path = sauvegarder(
            data,
            metadata_path,
        )

        print(
            f"Chunks modifiés : "
            f"{application['modifies']}"
        )

        print(
            f"Chunks nettoyés : "
            f"{application['nettoyes']}"
        )

        print(
            f"Backup créé : "
            f"{backup_path}"
        )

        print()
        print(
            "metadata.json mis à jour."
        )

        print(
            "FAISS : inchangé."
        )

        print(
            "RBAC : inchangé."
        )

        print(
            "allowed_roles : inchangé."
        )

        print(
            "access_roles : inchangé."
        )

        print(
            "departement (singulier) : inchangé."
        )

        print(
            "type_document : inchangé."
        )

        print(
            "public_reglementaire : inchangé."
        )

    # ------------------------------------------------------------------------
    # MODE DRY RUN
    # ------------------------------------------------------------------------

    else:

        print()
        print(
            "============================================================"
        )
        print(
            "MODE DRY-RUN"
        )
        print(
            "============================================================"
        )

        print(
            "Aucune modification de metadata.json."
        )

        print(
            "FAISS : inchangé."
        )

        print(
            "RBAC : inchangé."
        )

        print(
            "Pour appliquer les résultats :"
        )

        print(
            'python "classify_enterprise_departments.py" --apply'
        )


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()


# ============================================================================
# CHANGELOG
# ============================================================================
#
# v9.3 (corrigé complet)
# --------------
# 1. finance_exclue() ne coupe plus tout le score "bilan" du chunk :
#    seules les occurrences réellement rattachées à une expression
#    exclue (bilan carbone, bilan energetique, ...) sont retirées.
#    -> corrige les faux négatifs type Wafa_Assurance page 114.
#
# 2. finance_macro_exclue() est désormais appelée dans
#    validation_finance : un chunk purement macro-économique sans
#    terme "fort" finance n'est plus classé finance par erreur.
#
# 3. Ajout de fallbacks "contexte_it", "contexte_commerce" et
#    "contexte_marketing", symétriques à ceux qui existaient déjà pour
#    direction/finance/rh, pour réduire l'écart artificiel de
#    non-classés entre départements.
#
# 4. Seuils de répétition abaissés :
#      IT_REPETITION["donnee"]         4 -> 3
#      IT_REPETITION["innovation"]     4 -> 3
#      COMMERCE_REPETITION["marche"]   4 -> 3
#      MARKETING_REPETITION["communication"] 4 -> 3
#
# v9.3 :
# 5. Chemin metadata robuste : backend/data/index/metadata.json par défaut,
#    avec --metadata en override et recherche de secours.
# 6. Correction de la détection des titres "table des matières"/"contents"/etc.
#    dans les sommaires/index.
# 7. Canonicalisation renforcée des expressions : états financiers -> état
#    financier, comptes annuels -> compte annuel, données personnelles ->
#    donnée personnelle.
# 8. Renforcement de la couverture finance assurantielle : placements,
#    engagements techniques, primes émises, sinistres, résultat technique,
#    etc., sans faire de "produit"/"charge" des signaux forts isolés.
# 9. Renforcement direction sur les formulations "stratégique + ambition/
#    vision/perspective".
# 10. Renforcement juridique pour les formulations réglementaires
#     (loi, dahir, indemnisation, code des assurances, etc.).
# 11. Nettoyage des champs classifier limité aux sources classifier_v* ;
#     aucune autre métadonnée n'est supprimée.
#
# A valider en dry-run avant tout --apply :
#   python "classify enterprise departments.py" --show-limite 0 --show-non-classes 0
# Puis seulement après validation :
#   python "classify enterprise departments.py" --apply