"""Analyse de fichiers televerses (PDF, Word, texte, CSV).

Ephemere : le contenu reste en memoire, jamais sur disque ni en base.
Le fichier est une source NON FIABLE : validation du format, limites de
taille, filtre d'injection indirecte sur chaque extrait.
"""

import hashlib
import io
import math
import os
import re
import time
import unicodedata
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from rag.generation import generate_answer
from rag.postcheck import verifier_fondement
from rag.security import MESSAGE_SORTIE_INVALIDE, detecter_extrait, sortie_fuite_prompt

try:
    import pymupdf
except ImportError:  # anciennes versions de PyMuPDF
    import fitz as pymupdf

MAX_OCTETS = 5 * 1024 * 1024
MAX_PAGES = 80
MAX_CARACTERES = 400_000
TAILLE_EXTRAIT = 1200
CHEVAUCHEMENT = 150
TOP_K = 6
TAILLE_PAGE_VIRTUELLE = 3000
EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".csv")
DUREE_VIE_S = 30 * 60
MAX_PAR_UTILISATEUR = 3


class FichierRefuse(ValueError):
    """Fichier refuse : le message est affichable tel quel a l'utilisateur."""


@dataclass
class Fichier:
    id: str
    nom: str
    ext: str
    taille: int
    sha: str
    pages: int
    chunks: List[Dict[str, Any]]
    bloques: List[Dict[str, Any]] = field(default_factory=list)
    avertissements: List[str] = field(default_factory=list)
    tenant_id: str = ""
    user_id: str = ""
    cree: float = field(default_factory=time.time)


# ----------------------------------------------------------------- lecture

def _nom_propre(nom: str) -> str:
    base = os.path.basename((nom or "").replace("\\", "/")) or "fichier"
    base = re.sub(r"[^\w .\-()]", "_", base, flags=re.UNICODE)
    return base[:100]


def _paginer(texte: str) -> List[Tuple[int, str]]:
    pages, courant, n = [], "", 1
    for ligne in texte.splitlines():
        if courant and len(courant) + len(ligne) > TAILLE_PAGE_VIRTUELLE:
            pages.append((n, courant))
            courant, n = "", n + 1
        courant += ligne + "\n"
    if courant.strip():
        pages.append((n, courant))
    return pages


def _lire_pdf(data: bytes) -> Tuple[List[Tuple[int, str]], List[str]]:
    if not data.startswith(b"%PDF-"):
        raise FichierRefuse("Ce fichier n'est pas un vrai PDF.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise FichierRefuse("PDF illisible ou corrompu.")
    if doc.needs_pass or doc.is_encrypted:
        raise FichierRefuse("PDF protégé par mot de passe : retirez la protection puis réessayez.")
    if doc.page_count > MAX_PAGES:
        raise FichierRefuse("PDF trop long (%d pages, maximum %d)." % (doc.page_count, MAX_PAGES))
    pages, sans_texte = [], 0
    for i in range(doc.page_count):
        t = doc[i].get_text("text") or ""
        if len(t.strip()) < 20:
            sans_texte += 1
        else:
            pages.append((i + 1, t))
    if not pages:
        raise FichierRefuse(
            "Ce PDF ne contient pas de texte lisible (document scanné ou images). "
            "La lecture des images arrive avec la prochaine étape.")
    avert = []
    if sans_texte:
        avert.append("%d page(s) sans texte (images ou scan) n'ont pas pu être lues." % sans_texte)
    return pages, avert


def _lire_docx(data: bytes) -> Tuple[List[Tuple[int, str]], List[str]]:
    if not data.startswith(b"PK"):
        raise FichierRefuse("Ce fichier n'est pas un vrai document Word (.docx).")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > 100 * 1024 * 1024:
                raise FichierRefuse("Document Word refusé (contenu décompressé trop volumineux).")
            if "word/document.xml" not in z.namelist():
                raise FichierRefuse("Ce fichier n'est pas un vrai document Word (.docx).")
        from docx import Document
        d = Document(io.BytesIO(data))
        lignes = [p.text for p in d.paragraphs if p.text.strip()]
        for tableau in d.tables:
            for ligne in tableau.rows:
                cellules = [c.text.strip() for c in ligne.cells]
                if any(cellules):
                    lignes.append(" | ".join(cellules))
    except FichierRefuse:
        raise
    except Exception:
        raise FichierRefuse("Document Word illisible ou corrompu.")
    texte = "\n\n".join(lignes)
    if not texte.strip():
        raise FichierRefuse("Ce document Word ne contient pas de texte.")
    return _paginer(texte), []


def _lire_texte(data: bytes) -> Tuple[List[Tuple[int, str]], List[str]]:
    if b"\x00" in data[:4096]:
        raise FichierRefuse("Ce fichier n'est pas un fichier texte.")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            texte = data.decode(enc)
            break
        except UnicodeDecodeError:
            texte = ""
    if not texte.strip():
        raise FichierRefuse("Fichier vide ou encodage non reconnu.")
    return _paginer(texte), []


# --------------------------------------------------------------- decoupage

def _termes(s: str) -> List[str]:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    out = []
    for t in re.findall(r"[a-z0-9]+", s):
        if t in _STOP or len(t) < 2:
            continue
        if len(t) > 3 and t[-1] in "sx":
            t = t[:-1]
        out.append(t)
    return out


_STOP = set((
    "le la les un une des du de d l et ou a au aux en dans sur pour par avec sans que qui quoi "
    "quel quelle quels quelles est sont ete etre il elle ils elles on ce cet cette ces se sa son "
    "ses leur leurs ne pas plus comment combien quand pourquoi dit selon document fichier pdf "
    "texte donne moi dis y a t ai as").split())


def _mk(texte: str, page: int, entete: str) -> Dict[str, Any]:
    contenu = texte
    if entete and not texte.startswith(entete):
        contenu = entete + "\n" + texte
    return {"content": contenu, "page": page, "tf": Counter(_termes(contenu))}


def _decouper(pages: List[Tuple[int, str]], entete: str = "") -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    sep = "\n" if entete else "\n\n"
    motif = r"\n" if entete else r"\n\s*\n"
    for num, texte in pages:
        courant = ""
        for u in [x.strip() for x in re.split(motif, texte) if x.strip()]:
            while len(u) > TAILLE_EXTRAIT:
                if courant:
                    chunks.append(_mk(courant, num, entete))
                    courant = ""
                chunks.append(_mk(u[:TAILLE_EXTRAIT], num, entete))
                u = u[TAILLE_EXTRAIT - CHEVAUCHEMENT:]
            if courant and len(courant) + len(u) + 2 > TAILLE_EXTRAIT:
                chunks.append(_mk(courant, num, entete))
                courant = ""
            courant = courant + sep + u if courant else u
        if courant:
            chunks.append(_mk(courant, num, entete))
    return chunks


def _ecarter_lignes(pages):
    """Retire les lignes suspectes (injection) en gardant le reste de la page."""
    propres, bloques = [], []
    for num, texte in pages:
        lignes = texte.split("\n")
        garde, retire = [], False
        for l in lignes:
            v = detecter_extrait(l) if l.strip() else None
            if v is not None and v.bloque:
                bloques.append({"page": num, "categorie": v.categorie, "regle": v.regle})
                retire = True
            else:
                garde.append(l)
        t = "\n".join(garde) if retire else texte
        if t.strip():
            propres.append((num, t))
    return propres, bloques


def charger(nom: str, data: bytes) -> Fichier:
    nom = _nom_propre(nom)
    ext = os.path.splitext(nom)[1].lower()
    if ext not in EXTENSIONS:
        raise FichierRefuse(
            "Format non pris en charge (%s). Formats acceptés : PDF, Word (.docx), TXT, MD, CSV."
            % (ext or "sans extension"))
    if not data:
        raise FichierRefuse("Fichier vide.")
    if len(data) > MAX_OCTETS:
        raise FichierRefuse("Fichier trop volumineux (maximum %d Mo)." % (MAX_OCTETS // (1024 * 1024)))

    if ext == ".pdf":
        pages, avert = _lire_pdf(data)
    elif ext == ".docx":
        pages, avert = _lire_docx(data)
    else:
        pages, avert = _lire_texte(data)
    if sum(len(t) for _, t in pages) > MAX_CARACTERES:
        raise FichierRefuse("Contenu trop volumineux pour une analyse fiable.")

    entete = ""
    if ext == ".csv":
        entete = next((l.strip() for l in pages[0][1].splitlines() if l.strip()), "")[:400]

    pages, bloques = _ecarter_lignes(pages)
    brut = _decouper(pages, entete)
    chunks = []
    for c in brut:  # le fichier est non fiable : meme filtre que les documents indexes
        v = detecter_extrait(c["content"])
        if v.bloque:
            bloques.append({"page": c["page"], "categorie": v.categorie, "regle": v.regle})
        else:
            chunks.append(c)
    if not chunks:
        raise FichierRefuse("Le contenu de ce fichier a été bloqué par la politique de sécurité.")
    if bloques:
        avert.append("%d passage(s) suspect(s) ont été écartés par la politique de sécurité." % len(bloques))
    if ext == ".csv":
        avert.append("Fichier tabulaire : l'assistant lit et cite les lignes, il ne fait pas de calculs.")

    return Fichier(
        id=uuid.uuid4().hex, nom=nom, ext=ext, taille=len(data),
        sha=hashlib.sha256(data).hexdigest(), pages=len(pages), chunks=chunks,
        bloques=bloques, avertissements=avert)


# --------------------------------------------------------------- selection

_SYNTHESE = re.compile(
    r"resum|synthes|de quoi (parle|traite)|sujet (du|de ce)|points? cles?|principaux points|contenu (du|de ce)")


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(c) != "Mn")


def selectionner(chunks: List[Dict[str, Any]], question: str, k: int = TOP_K) -> List[Dict[str, Any]]:
    n = len(chunks)
    if not n:
        return []
    q = _termes(question)
    if _SYNTHESE.search(_fold(question)) or not q:
        if n <= k:
            return list(chunks)
        return [chunks[round(i * (n - 1) / (k - 1))] for i in range(k)]
    df = Counter()
    for c in chunks:
        for t in set(c["tf"]):
            df[t] += 1
    notes = []
    for i, c in enumerate(chunks):
        s = 0.0
        for t in set(q):
            f = c["tf"].get(t, 0)
            if f:
                s += math.log(1 + n / (1 + df[t])) * (1 + math.log(f))
        if s > 0:
            notes.append((s, i))
    notes.sort(reverse=True)
    return [chunks[i] for i in sorted(i for _, i in notes[:k])]


# ----------------------------------------------------------------- reponse

def _score(fo: Any) -> Optional[float]:
    if isinstance(fo, dict):
        fo = fo.get("score")
    return float(fo) if isinstance(fo, (int, float)) else None


def repondre(f: Fichier, question: str, role: str) -> Dict[str, Any]:
    sel = selectionner(f.chunks, question)
    if not sel:
        return {"answer": "Je ne trouve pas cette information dans le fichier « %s »." % f.nom,
                "fondement": None, "sources": [], "trouve": False}
    rag = [{
        "content": c["content"], "fichier_source": f.nom, "page": c["page"],
        "entreprise": "Fichier : " + f.nom, "type_document": "fichier_utilisateur",
        "type": "fichier_utilisateur", "departement": "", "score": 1.0,
        "demo": False, "verifie": False,
    } for c in sel]
    rep = generate_answer(question, rag, role)
    if isinstance(rep, dict):
        rep = rep.get("answer", "")
    rep = str(rep or "")
    if sortie_fuite_prompt(rep):
        return {"answer": MESSAGE_SORTIE_INVALIDE, "fondement": None, "sources": [], "trouve": True}
    cites = sorted({int(m) for m in re.findall(r"\[(?:Source\s*)?(\d+)", rep) if 0 < int(m) <= len(rag)})
    cites = cites or list(range(1, len(rag) + 1))
    sources = [{"n": i, "fichier": f.nom, "page": rag[i - 1]["page"], "entreprise": "Fichier téléversé",
                "type": "fichier_utilisateur", "demo": False, "verifie": False} for i in cites]
    return {"answer": rep, "fondement": _score(verifier_fondement(rep, rag)),
            "sources": sources, "trouve": True}
