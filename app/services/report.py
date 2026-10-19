"""Rapport PDF des indicateurs verifies.

Genere avec reportlab, sans LLM : le contenu est la liste deja filtree par
role (kpi_visibles). Chaque valeur est accompagnee de sa source.
"""

from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

VERT = colors.HexColor("#0f766e")
GRIS = colors.HexColor("#475569")
PERIMETRES = {
    "social": "Comptes sociaux",
    "consolide": "Consolidé",
    "non_precise": "Périmètre non précisé",
}


def fmt_valeur(v: float) -> str:
    s = f"{v:,.3f}".rstrip("0").rstrip(".")
    return s.replace(",", " ").replace(".", ",")


def fmt_variation(v: float) -> str:
    signe = "+" if v > 0 else "-" if v < 0 else ""
    return f"{signe}{abs(v):.1f}".replace(".", ",") + " %"


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle("titre", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=20, textColor=VERT, alignment=0, spaceAfter=4),
        "meta": ParagraphStyle("meta", parent=base["Normal"], fontSize=9, textColor=GRIS, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=13, spaceBefore=12, spaceAfter=6),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=8.5, leading=11),
        "head": ParagraphStyle("head", parent=base["Normal"], fontName="Helvetica-Bold",
                               fontSize=8.5, textColor=colors.white),
        "note": ParagraphStyle("note", parent=base["Normal"], fontSize=8, leading=10.5,
                               textColor=GRIS, spaceBefore=12),
    }


def _tableau(items: List[Dict[str, Any]], st: Dict[str, ParagraphStyle]) -> Table:
    entetes = ["Indicateur", "Exercice", "Valeur", "Périmètre", "Variation", "Source"]
    lignes = [[Paragraph(e, st["head"]) for e in entetes]]
    for k in items:
        ind = escape(str(k["libelle"]))
        if k.get("verifie"):
            ind += " <font size='7' color='#0f766e'>(vérifiée)</font>"
        if k.get("avertissement"):
            ind += "<br/><font size='7' color='#b45309'>" + escape(str(k["avertissement"])) + "</font>"
        var = "-"
        if k.get("variation_pct") is not None and k.get("annee_precedente") is not None:
            var = f"{fmt_variation(k['variation_pct'])} vs {k['annee_precedente']}"
        source = escape(str(k["document"]).replace("_", " ")) + f", p. {k['page']}"
        lignes.append([
            Paragraph(ind, st["cell"]),
            Paragraph(str(k["annee"]), st["cell"]),
            Paragraph(f"<b>{fmt_valeur(k['valeur'])}</b> {escape(str(k['unite']))}", st["cell"]),
            Paragraph(PERIMETRES.get(k["perimetre"], PERIMETRES["non_precise"]), st["cell"]),
            Paragraph(var, st["cell"]),
            Paragraph(source, st["cell"]),
        ])
    t = Table(lignes, colWidths=[7.5 * cm, 2 * cm, 4 * cm, 3.7 * cm, 3.5 * cm, 6 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _pied(role: str):
    def dessiner(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRIS)
        canvas.drawString(1.5 * cm, 1 * cm, f"Fluxa - document confidentiel - profil {role}")
        canvas.drawRightString(landscape(A4)[0] - 1.5 * cm, 1 * cm, f"Page {doc.page}")
        canvas.restoreState()
    return dessiner


def build_kpi_pdf(items: List[Dict[str, Any]], *, role: str, user: str,
                  generated_at: datetime) -> bytes:
    """items = sortie de kpi_visibles(role, ...) : deja filtree par role."""
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.8 * cm,
        title="Fluxa - Indicateurs vérifiés", author="Fluxa")
    quand = generated_at.strftime("%d/%m/%Y %H:%M") + " UTC"
    flow: list = [
        Paragraph("Indicateurs vérifiés", st["titre"]),
        Paragraph(f"Généré le {quand} · Profil : {escape(str(role))} · "
                  f"Utilisateur : {escape(str(user))} · {len(items)} indicateur(s)", st["meta"]),
    ]
    groupes: Dict[str, List[Dict[str, Any]]] = {}
    for k in items:
        groupes.setdefault(k["entreprise"], []).append(k)
    for nom, liste in groupes.items():
        flow.append(Paragraph(escape(nom), st["h2"]))
        flow.append(_tableau(liste, st))
    flow.append(Paragraph(
        "Chaque valeur est reprise du document et de la page indiqués, et contrôlée dans le texte "
        "de cette page. La variation n'est calculée qu'entre deux exercices de même périmètre "
        "précisé. Ce rapport ne contient que les indicateurs accessibles à votre profil.", st["note"]))
    pied = _pied(str(role))
    doc.build(flow, onFirstPage=pied, onLaterPages=pied)
    return buf.getvalue()
