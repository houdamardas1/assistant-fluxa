#!/usr/bin/env python3
"""
Ingestion des rapports financiers AMMC.

Extrait le texte de chaque PDF, le decoupe en chunks (RecursiveCharacterTextSplitter),
detecte la page d'origine de chaque chunk, et ecrit pour chaque PDF un fichier
data/raw/<secteur>/<entreprise>/<fichier>_chunks.json.

Prerequis :
    pip install pdfplumber langchain

Usage:
    python ingest_reports.py
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

import pdfplumber
from langchain.text_splitter import RecursiveCharacterTextSplitter


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

BASE_PATH = Path("data/raw")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
LOW_TEXT_THRESHOLD = 50


# ---------------------------------------------------------------------------
# RBAC : roles autorises par secteur pour les documents ENTREPRISE
# ---------------------------------------------------------------------------
# Les rapports financiers des entreprises sont limites aux roles metier
# correspondant au perimetre autorise.
SECTOR_ROLES = {
    "assurance":       ["tous", "finance", "direction"],
    "finance":         ["tous", "finance", "direction"],
    "agroalimentaire": ["tous", "finance", "direction"],
    "automobile":      ["tous", "finance", "direction"],
}

# Repli restrictif pour un secteur entreprise inconnu.
DEFAULT_ROLES = ["direction"]


# ---------------------------------------------------------------------------
# Roles pour les documents publics/reglementaires
# ---------------------------------------------------------------------------
# Les textes de loi, codes et directives sont publics et doivent etre
# accessibles a tous les roles metier.
PUBLIC_REGLEMENTAIRE_ROLES = [
    "tous",
    "finance",
    "direction",
    "it",
    "rh",
    "commerce",
    "juridique",
    "marketing",
]


def extract_pages(pdf_path: Path) -> tuple[list[dict], list[int]]:
    """
    Extrait le texte page par page.

    Retourne (pages, low_text_pages) :
      - pages : [{"page": n, "text": "..."}]
      - low_text_pages : numeros de page dont le texte est tres court
        (candidats a un scan ou une page d'illustration).
    """

    pages = []
    low_text_pages = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            pages.append({
                "page": i,
                "text": text,
            })

            if len(text.strip()) < LOW_TEXT_THRESHOLD:
                low_text_pages.append(i)

    return pages, low_text_pages


def chunk_pages(pages: list[dict]) -> list[dict]:
    """
    Chunk le texte de chaque page en gardant la page d'origine.

    Le decoupage est fait page par page.
    """

    chunks = []

    for page_data in pages:
        page_num = page_data["page"]
        page_text = page_data["text"]

        if not page_text.strip():
            continue

        for chunk_text in splitter.split_text(page_text):

            if len(chunk_text.strip()) < 50:
                continue

            chunks.append({
                "page": page_num,
                "content": chunk_text,
            })

    return chunks


# ---------------------------------------------------------------------------
# Text splitter
# ---------------------------------------------------------------------------

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
    length_function=len,
)


def detect_type_document(pdf_path: Path) -> str:
    """
    Determine le type du document a partir du nom du fichier.

    Retourne :
      - public_reglementaire
      - entreprise
    """

    nom_lower = pdf_path.name.lower()

    if (
        nom_lower.startswith("loi")
        or "code_du_travail" in nom_lower
        or "code_de_commerce" in nom_lower
        or "code_obligations" in nom_lower
        or "dnssi" in nom_lower
        or "directive_securite" in nom_lower
    ):
        return "public_reglementaire"

    return "entreprise"


def determine_allowed_roles(
    secteur: str,
    entreprise: str,
    type_document: str,
) -> list[str]:
    """
    Determine les roles autorises selon le type de document.

    Regle de securite :
      - document public_reglementaire -> tous les roles metier
      - document entreprise -> roles du secteur
      - secteur entreprise inconnu -> direction uniquement
    """

    # -------------------------------------------------------------------
    # Documents publics/reglementaires
    # -------------------------------------------------------------------
    if type_document == "public_reglementaire":
        return PUBLIC_REGLEMENTAIRE_ROLES.copy()

    # -------------------------------------------------------------------
    # Documents entreprise
    # -------------------------------------------------------------------
    roles = SECTOR_ROLES.get(secteur)

    if roles is None:
        logger.warning(
            f"  Secteur inconnu '{secteur}' pour {entreprise} - "
            f"acces restreint a {DEFAULT_ROLES} par defaut. "
            f"Ajoute '{secteur}' a SECTOR_ROLES si c'est voulu."
        )

        return DEFAULT_ROLES.copy()

    return roles.copy()


def process_pdf(pdf_path: Path) -> dict | None:
    """
    Traite un PDF complet :
      1. extraction
      2. chunking
      3. detection du type
      4. attribution RBAC
      5. creation des metadonnees
    """

    secteur = pdf_path.parent.parent.name
    entreprise = pdf_path.parent.name

    logger.info(
        f"Traitement : {entreprise} ({secteur}) - {pdf_path.name}"
    )

    # -------------------------------------------------------------------
    # Extraction
    # -------------------------------------------------------------------

    pages, low_text_pages = extract_pages(pdf_path)

    total_text = sum(
        len(page["text"])
        for page in pages
    )

    if total_text == 0:
        logger.warning(
            "  Aucun texte extrait du tout - PDF probablement scanne, "
            "OCR necessaire"
        )
        return None

    # -------------------------------------------------------------------
    # Chunking
    # -------------------------------------------------------------------

    chunks = chunk_pages(pages)

    # -------------------------------------------------------------------
    # Type de document
    # -------------------------------------------------------------------
    # IMPORTANT :
    # Le type doit etre determine AVANT les roles RBAC.
    # Les documents publics/reglementaires ne dependent pas du secteur.
    # -------------------------------------------------------------------

    type_document = detect_type_document(pdf_path)

    # -------------------------------------------------------------------
    # RBAC
    # -------------------------------------------------------------------

    roles = determine_allowed_roles(
        secteur=secteur,
        entreprise=entreprise,
        type_document=type_document,
    )

    # -------------------------------------------------------------------
    # Pages avec peu de texte
    # -------------------------------------------------------------------

    if low_text_pages:
        pct = len(low_text_pages) / len(pages) * 100

        logger.info(
            f"  {len(low_text_pages)}/{len(pages)} pages "
            f"({pct:.0f}%) ont peu de texte "
            f"(< {LOW_TEXT_THRESHOLD} car.) - "
            f"a verifier manuellement si important : "
            f"{low_text_pages[:10]}"
        )

    # -------------------------------------------------------------------
    # Metadata
    # -------------------------------------------------------------------

    result = {
        "entreprise": entreprise,
        "secteur": secteur,
        "fichier_source": pdf_path.name,

        "nb_pages_total": len(pages),
        "nb_pages_low_text": len(low_text_pages),
        "pages_low_text": low_text_pages,

        "nb_chunks": len(chunks),

        "allowed_roles": roles,
        "type_document": type_document,

        "processed_at": datetime.now(timezone.utc).isoformat(),

        "chunks": chunks,
    }

    logger.info(
        f"  -> {len(pages)} pages, "
        f"{total_text} caracteres, "
        f"{len(chunks)} chunks | "
        f"roles={roles} | "
        f"type={type_document}"
    )

    return result


def main():
    """
    Lance l'ingestion de tous les PDFs presents dans data/raw/.
    """

    pdf_files = list(
        BASE_PATH.glob("**/*.pdf")
    )

    if not pdf_files:
        logger.error(
            f"Aucun PDF trouve dans {BASE_PATH.resolve()} - "
            f"lance depuis backend/"
        )
        return

    logger.info(
        f"{len(pdf_files)} PDFs trouves"
    )

    summary = []

    for pdf_path in pdf_files:

        result = process_pdf(pdf_path)

        if not result:
            continue

        # -------------------------------------------------------------------
        # Ecriture du JSON correspondant au PDF
        # -------------------------------------------------------------------

        out_path = (
            pdf_path.parent
            / f"{pdf_path.stem}_chunks.json"
        )

        with open(
            out_path,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                result,
                f,
                ensure_ascii=False,
                indent=2,
            )

        summary.append({
            "entreprise": result["entreprise"],
            "secteur": result["secteur"],
            "type_document": result["type_document"],
            "allowed_roles": result["allowed_roles"],
            "nb_pages_total": result["nb_pages_total"],
            "nb_pages_low_text": result["nb_pages_low_text"],
            "nb_chunks": result["nb_chunks"],
        })

    # -----------------------------------------------------------------------
    # Summary global
    # -----------------------------------------------------------------------

    summary_path = (
        BASE_PATH / "ingestion_summary.json"
    )

    with open(
        summary_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {
                "ingestion_date": datetime.now(
                    timezone.utc
                ).isoformat(),

                "documents": summary,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # -----------------------------------------------------------------------
    # Resume console
    # -----------------------------------------------------------------------

    logger.info("\n" + "=" * 60)
    logger.info("RESUME")
    logger.info("=" * 60)

    for s in summary:

        logger.info(
            f"  {s['entreprise']} "
            f"[{s['secteur']}/{s['type_document']}] : "
            f"{s['nb_chunks']} chunks "
            f"({s['nb_pages_low_text']}/"
            f"{s['nb_pages_total']} pages a faible texte) "
            f"| roles={s['allowed_roles']}"
        )


if __name__ == "__main__":
    main()