"""
Verification APRES generation, deterministe (aucun appel LLM, aucun token).

Pour chaque ligne factuelle de la reponse (une puce = une unite, car le modele
cite en fin de puce) :
  1. porte-t-elle au moins une citation [Source N] valide (1..nb extraits) ?
  2. chaque nombre d'au moins 2 chiffres figure-t-il dans les extraits cites ?
  3. (indicatif) ses termes distinctifs figurent-ils dans ces extraits ?

Le score de fondement est la part des unites qui passent 1 et 2. Le controle 3
est rapporte a part : il n'entre pas dans le score tant que son seuil n'est pas
calibre sur des cas etiquetes.
Les nombres ecrits en lettres ("cinquante-deux") sont convertis des deux cotes ;
seuls les nombres d'au moins 2 chiffres sont controles, et un ecart signifie
"a verifier", pas "faux".
"""

import re
import unicodedata
from typing import Any, Dict, List

MIN_MOTS = 6
SEUIL_LEXICAL = 2

RE_CITATION = re.compile(
    r"\[\s*Sources?\s*\d+(?:\s*[,;]\s*(?:Sources?\s*)?\d+)*\s*\]", re.IGNORECASE
)
RE_NOMBRE = re.compile(r"\d{1,3}(?:[ \u00a0\u202f.]\d{3})+(?:,\d+)?|\d+(?:,\d+)?")
RE_PUCE = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")

STOP = {
    "cette", "leurs", "entre", "apres", "avant", "selon", "ainsi", "comme",
    "chaqu", "toute", "depui", "lorsq", "autre", "notam", "egale", "ayant",
    "doive", "peuve", "avoir", "etant", "aupre", "moins", "penda", "conce",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _canon(token: str) -> str:
    return re.sub(r"\D", "", token)


def _termes(s: str) -> Dict[str, str]:
    """{racine de 5 lettres: mot} pour les mots distinctifs d'au moins 5 lettres."""
    out: Dict[str, str] = {}
    for w in re.findall(r"[a-z]{5,}", _norm(s)):
        st = w[:5]
        if st not in STOP:
            out.setdefault(st, w)
    return out


_UNITES = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
}


def _nombres_en_lettres(texte: str) -> set:
    """Nombres francais ecrits en lettres (>= 10) en chiffres canoniques :
    'cinquante-deux' -> '52', 'quatre-vingt-dix' -> '90'."""
    trouves = set()
    total = courant = 0
    prev = None
    actif = False

    def clore():
        nonlocal total, courant, prev, actif
        if actif and total + courant >= 10:
            trouves.add(str(total + courant))
        total = courant = 0
        prev = None
        actif = False

    for w in re.findall(r"[a-z]+", _norm(texte)):
        if w in ("vingts", "cents"):
            w = w[:-1]
        if w in _UNITES:
            if w == "vingt" and prev == "quatre":
                courant += 76
            else:
                courant += _UNITES[w]
            actif, prev = True, w
        elif w == "cent":
            courant = (courant or 1) * 100
            actif, prev = True, w
        elif w == "mille":
            total += (courant or 1) * 1000
            courant = 0
            actif, prev = True, w
        elif w == "et" and actif:
            prev = w
        else:
            clore()
    clore()
    return trouves


def _indent(ligne: str) -> int:
    return len(ligne) - len(ligne.lstrip(" \t"))


def _citation_heritee(lignes: List[str], i: int) -> str:
    """Citation d'une puce imbriquee (indentee) sans citation propre : celle de la
    premiere puce suivante du MEME niveau, dans le meme bloc (pas de ligne vide).
    Les puces de premier niveau n'heritent de rien."""
    if RE_CITATION.search(lignes[i]) or not RE_PUCE.match(lignes[i]):
        return ""
    niveau = _indent(lignes[i])
    if niveau == 0:
        return ""
    for suite in lignes[i + 1:]:
        if not suite.strip() or _indent(suite) < niveau:
            return ""
        if _indent(suite) == niveau and RE_PUCE.match(suite):
            trouvees = [m.group(0) for m in RE_CITATION.finditer(suite)]
            if trouvees:
                return " ".join(trouvees)
    return ""


def verifier_fondement(texte: str, rag_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    nb = len(rag_results or [])
    unites = supportees = non_citees = nombres_nok = lexical_nok = 0
    details: List[Dict[str, Any]] = []

    lignes = (texte or "").splitlines()
    for i, ligne in enumerate(lignes):
        brut = RE_PUCE.sub("", ligne).strip()
        if not brut or brut.endswith(":"):
            continue
        sans_cit = RE_CITATION.sub(" ", brut)
        if len(sans_cit.split()) < MIN_MOTS:
            continue
        unites += 1

        cites = sorted({
            int(n)
            for m in RE_CITATION.finditer(brut + " " + _citation_heritee(lignes, i))
            for n in re.findall(r"\d+", m.group(0))
            if 1 <= int(n) <= nb
        })
        if not cites:
            non_citees += 1
            details.append({"texte": sans_cit.strip()[:160], "problemes": ["non_citee"]})
            continue

        corpus = "\n".join(rag_results[n - 1].get("content", "") for n in cites)
        problemes: List[str] = []
        info: Dict[str, Any] = {"texte": sans_cit.strip()[:160], "sources": cites}

        voulus = {_canon(t) for t in RE_NOMBRE.findall(sans_cit)}
        voulus = {n for n in voulus if len(n) >= 2}
        voulus |= _nombres_en_lettres(sans_cit)
        presents = {_canon(t) for t in RE_NOMBRE.findall(corpus)} | _nombres_en_lettres(corpus)
        absents = sorted(voulus - presents)
        if absents:
            problemes.append("nombre_non_soutenu")
            info["nombres"] = absents
            nombres_nok += 1

        dispo = _termes(corpus)
        manquants = sorted(w for st, w in _termes(sans_cit).items() if st not in dispo)
        if len(manquants) >= SEUIL_LEXICAL:
            problemes.append("a_verifier_lexical")
            info["termes"] = manquants
            lexical_nok += 1

        if not absents:
            supportees += 1
        if problemes:
            info["problemes"] = problemes
            details.append(info)

    return {
        "score": round(supportees / unites, 2) if unites else None,
        "unites": unites,
        "non_citees": non_citees,
        "nombres_non_soutenus": nombres_nok,
        "a_verifier_lexical": lexical_nok,
        "details": details,
    }
