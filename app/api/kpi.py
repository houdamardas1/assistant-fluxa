"""
API de consultation de la table de KPI verifies (data/kpi/kpi_v1.json).

SECURISE : authentification obligatoire ; un KPI n'est renvoye que si le role
de l'appelant figure dans roles_autorises (meme regle que le raccourci KPI du
pipeline). Aucun LLM : la variation est un calcul deterministe entre deux
valeurs verifiees de la table, uniquement a perimetre identique et precise.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.security.auth import Principal
from app.security.deps import client_ip, get_principal
from app.services.report import build_kpi_pdf
from rag.kpi import charger_kpi

router = APIRouter(prefix="/kpi", tags=["KPI"])


def kpi_visibles(role: str, kpi: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """KPI autorises pour ce role, avec la variation vs l'annee precedente."""
    visibles = [k for k in kpi if role in k.get("roles_autorises", [])]
    index = {
        (k["entreprise"], k["indicateur"], k["perimetre"], k["annee"]): k
        for k in visibles
    }
    sortie: List[Dict[str, Any]] = []
    for k in visibles:
        prec = None
        if k["perimetre"] != "non_precise":
            prec = index.get(
                (k["entreprise"], k["indicateur"], k["perimetre"], k["annee"] - 1)
            )
        variation = None
        if prec is not None and prec["valeur"]:
            variation = round((k["valeur"] - prec["valeur"]) / prec["valeur"] * 100, 1)
        sortie.append({
            "id": k["id"],
            "entreprise": k["entreprise"].replace("_", " "),
            "indicateur": k["indicateur"],
            "libelle": k.get("libelle") or k["indicateur"],
            "annee": k["annee"],
            "valeur": k["valeur"],
            "unite": k["unite"],
            "perimetre": k["perimetre"],
            "document": k["document"],
            "page": k["page"],
            "detail": k.get("note"),
            "avertissement": k.get("avertissement"),
            "verifie": k.get("statut") == "verifie_extrait",
            "annee_precedente": prec["annee"] if prec else None,
            "valeur_precedente": prec["valeur"] if prec else None,
            "variation_pct": variation,
        })
    sortie.sort(key=lambda x: (x["entreprise"], x["indicateur"], x["perimetre"], -x["annee"]))
    return sortie


@router.get("")
async def list_kpi(
    principal: Principal = Depends(get_principal),
) -> List[Dict[str, Any]]:
    """KPI verifies accessibles au role de l'appelant."""
    return kpi_visibles(principal.role, charger_kpi())


@router.get("/report.pdf")
def report_pdf(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> Response:
    """Rapport PDF des KPI accessibles au role de l'appelant (meme filtre que GET /kpi)."""
    state = request.app.state
    cle = f"{principal.tenant_id}:{principal.user_id}"
    if not state.limiter.allow(cle):
        raise HTTPException(
            status_code=429,
            detail="Trop de requetes. Reessayez dans un instant.",
            headers={"Retry-After": str(state.limiter.retry_after(cle))},
        )

    items = kpi_visibles(principal.role, charger_kpi())
    if not items:
        raise HTTPException(status_code=404, detail="Aucun indicateur accessible avec votre profil.")

    maintenant = datetime.now(timezone.utc)
    pdf = build_kpi_pdf(items, role=principal.role, user=principal.user_id, generated_at=maintenant)
    state.audit.record(
        "REPORT_EXPORTED", uuid.uuid4().hex,
        question="Export PDF des indicateurs", mode="PDF",
        detail=f"kpi={len(items)} octets={len(pdf)}",
        tenant_id=principal.tenant_id, user_id=principal.user_id,
        role=principal.role, client_ip=client_ip(request),
    )
    return Response(
        content=pdf, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="fluxa-indicateurs-{maintenant:%Y%m%d}.pdf"',
            "Cache-Control": "no-store",
        },
    )
