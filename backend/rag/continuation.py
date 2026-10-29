"""Completion des extraits coupes au saut de page.

Le decoupage se fait page par page : la derniere phrase d'une page est coupee
(ex. '... un mois et demi par - 28 -') et sa suite est au debut du chunk de la
page suivante. On l'ajoute au dernier chunk de la page. Les embeddings ne
changent pas : seul le texte donne au generateur est complete.

A n'appliquer qu'aux textes lineaires (textes juridiques) : dans un rapport en
colonnes, le chunk suivant n'est PAS la suite de la phrase.
"""

import re

_RE_MARQUEUR_PAGE = re.compile(r"\s*-\s*\d+\s*-\s*$")
_FINS = ".;:!?)\"\u00bb"
MAX_SUITE = 350
MAX_COUPE = 250


def _sans_marqueur(texte: str) -> str:
    return _RE_MARQUEUR_PAGE.sub("", texte.strip())


def est_coupe(texte: str) -> bool:
    t = _sans_marqueur(texte)
    return bool(t) and t[-1] not in _FINS


def suite_de_phrase(texte_suivant: str) -> str:
    """Debut du chunk suivant jusqu'a la fin de la phrase ; vide si la suite
    ne commence pas par une minuscule (nouvelle phrase ou nouvel article)."""
    debut = texte_suivant.lstrip()
    if not debut or not debut[0].islower():
        return ""
    m = re.search(r"[.;:!?](?:\s|$)", debut[:MAX_SUITE])
    if m:
        return debut[:m.end()].strip()
    return debut[:MAX_COUPE].rsplit(" ", 1)[0].strip()


def completer_extraits(chunks: list, types=None) -> list:
    """Complete en place les derniers chunks de page coupes ; renvoie les
    indices modifies. Idempotent (marque 'continuation_page_suivante').
    types : ensemble de 'type_document' admis (None = tous)."""
    modifies = []
    for i in range(len(chunks) - 1):
        c, n = chunks[i], chunks[i + 1]
        if types is not None and c.get("type_document") not in types:
            continue
        if c.get("continuation_page_suivante"):
            continue
        if c.get("fichier_source") != n.get("fichier_source"):
            continue
        p, q = c.get("page"), n.get("page")
        if not (isinstance(p, int) and isinstance(q, int) and q == p + 1):
            continue
        texte = c.get("content") or ""
        if not est_coupe(texte):
            continue
        suite = suite_de_phrase(n.get("content") or "")
        if not suite:
            continue
        c["content"] = _sans_marqueur(texte) + " " + suite
        c["continuation_page_suivante"] = True
        modifies.append(i)
    return modifies
