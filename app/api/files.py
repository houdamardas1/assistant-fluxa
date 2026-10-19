"""Televersement et questions sur un fichier (ephemere, en memoire)."""

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.security.deps import client_ip, get_principal
from app.services import uploads
from rag.llm import mesurer_usage
from rag.security import MESSAGE_BLOQUE, detecter

router = APIRouter(prefix="/files", tags=["files"])


class FileInfo(BaseModel):
    file_id: str
    nom: str
    type: str
    taille: int
    pages: int
    extraits: int
    ecartes: int
    avertissements: List[str]
    expire_dans: int


class AskFileBody(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class FileAnswer(BaseModel):
    request_id: str
    answer: str
    mode: str
    departement: Optional[str] = None
    confidence: float = 0.0
    fondement: Optional[float] = None
    sources: List[Dict[str, Any]] = []


class Magasin:
    """Fichiers en memoire, par utilisateur, avec duree de vie."""

    def __init__(self):
        self._d: Dict[str, uploads.Fichier] = {}
        self._v = threading.Lock()

    def _purger(self):
        limite = time.time() - uploads.DUREE_VIE_S
        for k in [k for k, f in self._d.items() if f.cree < limite]:
            del self._d[k]

    def ajouter(self, f: uploads.Fichier):
        with self._v:
            self._purger()
            siens = sorted((x for x in self._d.values()
                            if x.tenant_id == f.tenant_id and x.user_id == f.user_id),
                           key=lambda x: x.cree)
            while len(siens) >= uploads.MAX_PAR_UTILISATEUR:
                del self._d[siens.pop(0).id]
            self._d[f.id] = f

    def obtenir(self, fid: str, tenant: str, user: str) -> Optional[uploads.Fichier]:
        with self._v:
            self._purger()
            f = self._d.get(fid)
            return f if f and f.tenant_id == tenant and f.user_id == user else None

    def retirer(self, fid: str, tenant: str, user: str) -> bool:
        with self._v:
            f = self._d.get(fid)
            if f and f.tenant_id == tenant and f.user_id == user:
                del self._d[fid]
                return True
            return False


def _magasin(request: Request) -> Magasin:
    st = request.app.state
    if getattr(st, "uploads", None) is None:
        st.uploads = Magasin()
    return st.uploads


def _limite(request: Request, principal: Any):
    cle = "%s:%s" % (principal.tenant_id, principal.user_id)
    if not request.app.state.limiter.allow(cle):
        raise HTTPException(status_code=429, detail="Trop de requetes. Reessayez dans un instant.",
                            headers={"Retry-After": str(request.app.state.limiter.retry_after(cle))})


def _qui(request: Request, p: Any) -> Dict[str, Any]:
    return dict(tenant_id=p.tenant_id, user_id=p.user_id, role=p.role, client_ip=client_ip(request))


def _info(f: uploads.Fichier) -> FileInfo:
    reste = max(0, int(f.cree + uploads.DUREE_VIE_S - time.time()))
    return FileInfo(file_id=f.id, nom=f.nom, type=f.ext.lstrip("."), taille=f.taille, pages=f.pages,
                    extraits=len(f.chunks), ecartes=len(f.bloques),
                    avertissements=f.avertissements, expire_dans=reste)


@router.post("", response_model=FileInfo)
async def televerser(request: Request, file: UploadFile = File(...),
                     principal: Any = Depends(get_principal)) -> FileInfo:
    state = request.app.state
    _limite(request, principal)
    qui = _qui(request, principal)
    rid = uuid.uuid4().hex
    data = await file.read(uploads.MAX_OCTETS + 1)
    nom = file.filename or "fichier"
    try:
        f = await run_in_threadpool(uploads.charger, nom, data, getattr(getattr(state, "rag", None), "model", None))
    except uploads.FichierRefuse as e:
        state.audit.record("FILE_REJECTED", rid, question="Fichier refusé : " + uploads._nom_propre(nom),
                           mode="FICHIER", detail=str(e)[:200], **qui)
        raise HTTPException(status_code=400, detail=str(e))
    f.tenant_id, f.user_id = principal.tenant_id, principal.user_id
    _magasin(request).ajouter(f)
    state.audit.record(
        "FILE_UPLOADED", rid, question="Téléversement : " + f.nom, mode="FICHIER",
        detail="type=%s octets=%d sha=%s pages=%d extraits=%d ecartes=%d"
               % (f.ext.lstrip("."), f.taille, f.sha[:12], f.pages, len(f.chunks), len(f.bloques)), **qui)
    for b in f.bloques:
        state.audit.record("DOCUMENT_BLOCKED", rid, question="Fichier téléversé : " + f.nom, mode="FICHIER",
                           detail="%s p.%s %s/%s" % (f.nom, b["page"], b["categorie"], b["regle"]), **qui)
    return _info(f)


@router.post("/{file_id}/ask", response_model=FileAnswer)
def poser_question(file_id: str, body: AskFileBody, request: Request,
                   principal: Any = Depends(get_principal)) -> FileAnswer:
    state = request.app.state
    _limite(request, principal)
    qui = _qui(request, principal)
    rid = uuid.uuid4().hex
    f = _magasin(request).obtenir(file_id, principal.tenant_id, principal.user_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable ou expiré. Téléversez-le à nouveau.")
    v = detecter(body.question)
    if v.bloque:
        state.audit.record("PROMPT_BLOCKED", rid, question=body.question, mode="BLOQUE",
                           detail="%s/%s (fichier)" % (v.categorie, v.regle), **qui)
        return FileAnswer(request_id=rid, answer=MESSAGE_BLOQUE, mode="BLOQUE")
    t0 = time.perf_counter()
    with mesurer_usage() as usage:
        res = uploads.repondre(f, body.question, principal.role, getattr(getattr(state, "rag", None), "model", None))
    ms = int((time.perf_counter() - t0) * 1000)
    state.audit.record(
        "FILE_ANALYZED", rid, question=body.question, mode="FICHIER", answer=res["answer"],
        fondement=res["fondement"], latency_ms=ms,
        detail="fichier=%s sha=%s trouve=%s" % (f.nom, f.sha[:12], res["trouve"]),
        **usage.as_audit(), **qui)
    return FileAnswer(request_id=rid, answer=res["answer"], mode="FICHIER",
                      fondement=res["fondement"], sources=res["sources"])


@router.delete("/{file_id}")
def supprimer(file_id: str, request: Request, principal: Any = Depends(get_principal)) -> Dict[str, bool]:
    return {"supprime": _magasin(request).retirer(file_id, principal.tenant_id, principal.user_id)}
