"""Utilitaires texte : normalisation, nettoyage markdown, matching tolerant (accents, pluriels, tirets)."""

import re
import unicodedata


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
