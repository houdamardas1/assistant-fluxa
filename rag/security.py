"""Filtre d'entree : injection de prompt, fuite du prompt systeme, exfiltration.

Regles lexicales (FR / EN / AR / darija) appliquees AVANT tout appel au modele.
C'est une premiere barriere, pas une garantie (voir docs/LIMITES.md). Le role
vient du jeton : se declarer "admin" dans la question ne donne de toute facon
aucun droit.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

MESSAGE_BLOQUE = (
    "Cette demande ne peut pas \u00eatre trait\u00e9e : elle cherche \u00e0 contourner "
    "les r\u00e8gles de s\u00e9curit\u00e9 de l'assistant ou \u00e0 obtenir des informations "
    "internes. Reformulez votre question sur le contenu des documents."
)


@dataclass(frozen=True)
class Verdict:
    bloque: bool
    categorie: Optional[str] = None
    regle: Optional[str] = None


_ZERO = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_AR = {0x0649: 0x064A, 0x0640: None}   # alef maqsura -> ya ; tatweel supprime


def _norm(texte: str) -> str:
    """Minuscules, sans accents ni diacritiques, sans caracteres invisibles."""
    t = _ZERO.sub("", texte)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.translate(_AR).replace("\u2019", "'").lower()
    return re.sub(r"\s+", " ", t).strip()


_VERBES_IGNORER = (r"(?:ignor\w*|oubli\w*|desobei\w*|contourn\w*|desactiv\w*|neutralis\w*"
                   r"|disregard|forget|override|bypass|disable|circumvent)")
_CIBLES_REGLES = (r"(?:instructions?|consignes?|directives?|prompts?|restrictions?"
                  r"|garde-?fous?|guardrails?|rules|polic(?:y|ies)|politique de securite"
                  r"|regles de securite|security (?:rules|polic\w*)|filtres?)")
_VERBES_REVELER = (r"(?:affich\w*|montr\w*|revel\w*|donn\w*|dis|dites|repet\w*|ecri\w*"
                   r"|imprim\w*|copie\w*|print|show|reveal|display|repeat|leak|output"
                   r"|give|tell|dump)")
_CIBLES_PROMPT = (r"(?:prompts? systeme|system prompts?"
                  r"|(?:ton|tes|votre|vos|your|its)\s+(?:prompt|instructions?|consignes?"
                  r"|regles internes?|configuration)"
                  r"|instructions? (?:internes?|systeme|cachees?|initiales?)"
                  r"|configuration interne)")
_CIBLES_SECRETS = (r"(?:cles? api|api keys?|variables? d'environnement|environment variables"
                   r"|groq_api_key|jwt_secret|secret key|credentials"
                   r"|mots de passe des utilisateurs|users'? passwords?)")

_AR_VERBES_IGNORER = (r"(?:\u062a\u062c\u0627\u0647\u0644|\u0627\u0646\u0633\u064a"
                      r"|\u0627\u0647\u0645\u0644|\u062a\u062c\u0627\u0648\u0632"
                      r"|\u0639\u0637\u0644)\w*")
_AR_CIBLES_REGLES = (r"(?:\u0627\u0644\u062a\u0639\u0644\u064a\u0645\u0627\u062a"
                     r"|\u0627\u0644\u0627\u0648\u0627\u0645\u0631"
                     r"|(?:\u0627\u0644)?\u0642\u0648\u0627\u0639\u062f"
                     r"|\u0627\u0644\u0642\u064a\u0648\u062f"
                     r"|\u0627\u0644\u062a\u0648\u062c\u064a\u0647\u0627\u062a"
                     r"|\u0627\u0644\u0627\u0645\u0627\u0646)")
_AR_VERBES_REVELER = (r"(?:\u0627\u0638\u0647\u0631|\u0627\u0639\u0631\u0636"
                      r"|\u0627\u0643\u0634\u0641|\u0627\u0639\u0637\u0646\u064a"
                      r"|\u0627\u0637\u0628\u0639)\w*")
_AR_CIBLES_PROMPT = (r"(?:\u062a\u0639\u0644\u064a\u0645\u0627\u062a\u0643"
                     r"|\u0627\u0644\u0628\u0631\u0648\u0645\u0628\u062a)")

_REGLES = [
    ("INJECTION", "ignorer_instructions", re.compile(
        r"\b" + _VERBES_IGNORER + r"\b.{0,40}\b" + _CIBLES_REGLES + r"\b")),
    ("INJECTION", "changement_de_role", re.compile(
        r"\b(?:you are now|tu es maintenant|from now on,? you|a partir de maintenant,? tu"
        r"|desormais,? tu)\b")),
    ("INJECTION", "jailbreak", re.compile(
        r"\b(?:jailbreak\w*|do anything now|developer mode|mode developpeur|mode dieu)\b")),
    ("INJECTION", "sans_restriction", re.compile(
        r"\b(?:sans|without(?: any)?|no|aucune?)\s+(?:restrictions?|filtres?|garde-?fous?"
        r"|guardrails?)\b")),
    ("INJECTION", "balises_systeme", re.compile(
        r"(?:<\s*/?\s*(?:system|assistant|instructions?)\s*>|\[/?(?:system|inst)\]"
        r"|#{2,}\s*(?:system|instructions?)\b)")),
    ("INJECTION", "ar_ignorer_instructions", re.compile(
        _AR_VERBES_IGNORER + r".{0,30}" + _AR_CIBLES_REGLES)),
    ("INJECTION", "darija_ignorer_regles", re.compile(
        r"\b(?:nsa|tnsa|nsi|tjahal|tjahel)\b.{0,30}\b(?:l9awanin|9awanin|l9awaid"
        r"|lamane|l'amane|ta3limat|tawjihat)\b")),
    ("PROMPT_LEAK", "reveler_prompt", re.compile(
        r"\b" + _VERBES_REVELER + r"\b.{0,40}\b" + _CIBLES_PROMPT)),
    ("PROMPT_LEAK", "questions_sur_instructions", re.compile(
        r"(?:quelles? (?:sont|est) (?:tes|vos|votre|ton)|what (?:are|is) your)\s+"
        r"(?:instructions?|consignes?|regles|prompt|system prompt)")),
    ("PROMPT_LEAK", "ar_reveler_prompt", re.compile(
        _AR_VERBES_REVELER + r".{0,30}" + _AR_CIBLES_PROMPT)),
    ("EXFILTRATION", "tous_documents_confidentiels", re.compile(
        r"\b(?:tous|toutes|l'ensemble|all|every)\b.{0,30}\b(?:documents?|fichiers?|donnees"
        r"|files|records|dossiers)\b.{0,30}\b(?:confidentiel\w*|secret\w*|restreint\w*"
        r"|prives?|confidential|restricted|classified|sensibles?)\b")),
    ("EXFILTRATION", "export_massif", re.compile(
        r"\b(?:dump\w*|exporte\w*|export|extrais|extract|telecharge\w*|download)\b.{0,30}"
        r"\b(?:base de donnees|database|corpus|index|tous les (?:documents|fichiers"
        r"|utilisateurs|mots de passe)|all (?:documents|files|users|passwords))")),
    ("EXFILTRATION", "secrets_systeme", re.compile(
        r"\b" + _VERBES_REVELER + r"\b.{0,40}\b" + _CIBLES_SECRETS + r"\b")),
    ("ESCALADE", "elevation_de_privileges", re.compile(
        r"\b(?:change\w*|modifi\w*|passe\w*|elev\w*|escalat\w*|donn\w*|grant|give)\b.{0,25}"
        r"\b(?:mon role|my role|mes droits|my privileges|mes permissions"
        r"|mon niveau d'acces|acces admin\w*|admin access|mode admin\w*|droits admin\w*)\b")),
]


def detecter(question: str) -> Verdict:
    """Retourne le verdict du filtre d'entree pour une question."""
    t = _norm(question or "")
    for categorie, nom, motif in _REGLES:
        if motif.search(t):
            return Verdict(True, categorie, nom)
    return Verdict(False)
