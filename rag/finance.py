"""Regles metier financieres : familles, perimetre social/consolide, metrique litterale, indicateurs multiples, montants."""

import re

from .textutils import _norm, _regex_mots, contient_un_des_termes


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
