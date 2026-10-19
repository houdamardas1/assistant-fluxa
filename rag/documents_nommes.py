"""Reconnaissance d'un texte reglementaire nomme dans la question.

Le titre est derive du nom de fichier ("Code_Obligations_Contrats_DOC.pdf" ->
"Code Obligations Contrats DOC"). Un document est vise si TOUS les mots de 4
lettres ou plus de son titre (compares par leurs 5 premieres lettres, sans
accents) figurent dans la question, et s'il en compte au moins deux. Cette
regle est volontairement stricte : "Code des obligations" seul ne vise pas le
Code des Obligations et des Contrats.
"""

import re
import unicodedata
from pathlib import Path
from typing import Iterable, Set


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _racines(texte: str) -> Set[str]:
    return {w[:5] for w in re.findall(r"[a-z0-9]{4,}", _norm(texte))}


def titre_du_fichier(fichier: str) -> str:
    return re.sub(r"[_\-]+", " ", Path(fichier).stem)


def detect_documents_nommes(query: str, fichiers: Iterable[str]) -> Set[str]:
    q = _racines(query)
    vises: Set[str] = set()
    for f in set(fichiers):
        t = _racines(titre_du_fichier(f))
        if len(t) >= 2 and t <= q:
            vises.add(f)
    return vises


def corriger_type_question(q_type, resultats, can_answer):
    """Question visant un document nomme : jamais traitee en connaissance
    generale. Extraits valides -> RAG ("ENTREPRISE") ; sinon -> "ABSENTE"."""
    if q_type not in ("ENTREPRISE", "ABSENTE") and any(
        r.get("_document_nomme") for r in resultats
    ):
        return "ENTREPRISE" if can_answer else "ABSENTE"
    return q_type
