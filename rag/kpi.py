"""Raccourci KPI : reponse directe depuis une table de chiffres verifies.

Le raccourci ne repond que si la question designe SANS AMBIGUITE un seul KPI
(une entreprise, une metrique, une annee, un perimetre), si le role est
autorise ET si la valeur figure bien dans un passage de la page citee.
Dans tous les autres cas il rend la main au pipeline habituel : aucune
decision de refus n'est prise ici."""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from .finance import detect_metric, detect_scope
from .rbac import detect_entreprises

logger = logging.getLogger(__name__)

CHEMIN_KPI = Path(__file__).resolve().parents[1] / "data" / "kpi" / "kpi_v1.json"
_RE_ANNEE = re.compile(r"\b(?:19|20)\d{2}\b")
_LIBELLE = {
    "chiffre_affaires": "Chiffre d'affaires",
    "primes_emises": "Primes \u00e9mises",
    "revenus_assurance": "Revenus d'assurance",
    "resultat_net": "R\u00e9sultat net",
}
_PERIMETRE = {"social": " (comptes sociaux)", "consolide": " (consolid\u00e9)"}


@lru_cache(maxsize=1)
def charger_kpi() -> list:
    try:
        data = json.loads(CHEMIN_KPI.read_text(encoding="utf-8"))
        return list(data.get("kpi", []))
    except (OSError, ValueError) as e:
        logger.warning("KPI indisponibles (%s) : raccourci desactive.", e)
        return []


def formater_valeur(v) -> str:
    entier, _, dec = f"{v:,.3f}".partition(".")
    dec = dec.rstrip("0")
    return entier.replace(",", " ") + ("," + dec if dec else "")


def chercher_kpi(query, user_role, noms_entreprises, kpi=None):
    """Le KPI designe sans ambiguite par la question, ou None."""
    kpi = charger_kpi() if kpi is None else kpi
    if not kpi:
        return None

    metric = detect_metric(query)
    if metric not in _LIBELLE:
        return None

    annees = set(_RE_ANNEE.findall(query))
    if len(annees) != 1:
        return None
    annee = int(next(iter(annees)))

    entreprises = detect_entreprises(query, noms_entreprises)
    if len(entreprises) != 1:
        return None
    ent = next(iter(entreprises))

    scope = detect_scope(query)
    trouves = [
        k for k in kpi
        if k["entreprise"] == ent
        and k["indicateur"] == metric
        and k["annee"] == annee
        and (scope is None or k["perimetre"] == scope)
    ]
    if len(trouves) != 1:
        return None

    k = trouves[0]
    if user_role not in k["roles_autorises"]:
        return None
    return k


def trouver_passage(metadata, k):
    """Passage de la page citee qui contient reellement la valeur, ou None."""
    cibles = {formater_valeur(k["valeur"]).replace(" ", "")}
    cibles |= {c.replace(",", ".") for c in cibles}
    for c in metadata:
        if c.get("fichier_source") != k["document"]:
            continue
        if str(c.get("page")) != str(k["page"]):
            continue
        brut = re.sub(r"[\s\u00a0\u202f]", "", c.get("content", ""))
        if any(t in brut for t in cibles):
            return c
    return None


def formater_reponse(k) -> str:
    texte = "%s %s%s : %s %s [Source 1]" % (
        _LIBELLE[k["indicateur"]], k["annee"],
        _PERIMETRE.get(k["perimetre"], ""),
        formater_valeur(k["valeur"]), k["unite"],
    )
    if k.get("avertissement"):
        texte += "\n\n" + k["avertissement"]
    return texte


def repondre_depuis_kpi(query, user_role, metadata):
    """{'answer', 'passage', 'kpi'} ou None (le pipeline habituel prend alors la main)."""
    noms = {c.get("entreprise") for c in metadata if c.get("entreprise")}
    k = chercher_kpi(query, user_role, noms)
    if k is None:
        return None
    passage = trouver_passage(metadata, k)
    if passage is None:
        logger.warning(
            "KPI %s : valeur introuvable page %s de %s, raccourci ignore.",
            k["id"], k["page"], k["document"],
        )
        return None
    return {"answer": formater_reponse(k), "passage": passage, "kpi": k}
