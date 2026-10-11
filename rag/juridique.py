"""References juridiques : detection d'un numero d'article, titre d'article ou simple renvoi."""

import re


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
