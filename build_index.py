
#!/usr/bin/env python3
"""
Construit un index vectoriel FAISS local a partir des *_chunks.json
generes par ingest_reports.py. A executer depuis backend/, apres l'ingestion.

Usage:
    python build_index.py
"""

import json
import logging
from pathlib import Path

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_PATH = Path("data/raw")
INDEX_DIR = Path("data/index")

# Modele multilingue, gratuit, tourne en local (pas d'API key necessaire).
# Correct pour du francais financier ; ~470 Mo au premier telechargement.
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def load_all_chunks() -> list[dict]:
    """
    Charge tous les chunks depuis les fichiers *_chunks.json.

    Les metadonnees produites par ingest_reports.py sont conservees
    telles quelles :
      - entreprise
      - secteur
      - page
      - fichier_source
      - allowed_roles
      - is_synthetic
      - type_document

    IMPORTANT :
    build_index.py ne recalcule plus type_document.
    ingest_reports.py est la source de verite.
    """
    all_chunks = []

    for chunks_file in BASE_PATH.glob("**/*_chunks.json"):
        with open(chunks_file, "r", encoding="utf-8") as f:
            doc = json.load(f)

        entreprise = doc["entreprise"]
        secteur = doc["secteur"]
        fichier_source = doc["fichier_source"]

        # ------------------------------------------------------------------
        # RBAC : fallback restrictif.
        # Si allowed_roles est absent ou vide, on bloque par defaut.
        # ------------------------------------------------------------------
        allowed_roles = doc.get("allowed_roles")

        if not allowed_roles:
            logger.warning(
                f"  allowed_roles absent/vide pour {fichier_source} — "
                f"acces restreint a ['direction'] par defaut."
            )
            allowed_roles = ["direction"]

        # ------------------------------------------------------------------
        # Document synthetique : False par defaut.
        # ------------------------------------------------------------------
        is_synthetic = doc.get("is_synthetic", False)

        # ------------------------------------------------------------------
        # Type de document :
        # ingest_reports.py est la SEULE source de verite.
        # ------------------------------------------------------------------
        type_document = doc.get("type_document")

        if type_document is None:
            logger.warning(
                f"  type_document absent pour {fichier_source} — "
                f"classification 'entreprise' par defaut."
            )
            type_document = "entreprise"

        # ------------------------------------------------------------------
        # Propagation des metadonnees sur chaque chunk.
        # ------------------------------------------------------------------
        for chunk in doc["chunks"]:
            all_chunks.append({
                "content": chunk["content"],
                "page": chunk["page"],
                "entreprise": entreprise,
                "secteur": secteur,
                "fichier_source": fichier_source,
                "allowed_roles": allowed_roles,
                "is_synthetic": is_synthetic,
                "type_document": type_document,
            })

    return all_chunks


def build_index():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Chargement des chunks...")
    chunks = load_all_chunks()

    if not chunks:
        logger.error(
            f"Aucun chunk trouve dans {BASE_PATH.resolve()} "
            f"- lance d'abord ingest_reports.py"
        )
        return

    logger.info(f"{len(chunks)} chunks charges au total")

    logger.info(
        f"Chargement du modele d'embeddings ({MODEL_NAME})... "
        f"(peut telecharger ~470 Mo la premiere fois)"
    )
    model = SentenceTransformer(MODEL_NAME)

    logger.info("Calcul des embeddings...")

    texts = [c["content"] for c in chunks]

    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        convert_to_numpy=True
    )

    embeddings = embeddings.astype("float32")

    # Normalisation pour utiliser la similarite cosinus
    # avec un index produit scalaire.
    faiss.normalize_L2(embeddings)

    dimension = embeddings.shape[1]

    # Inner Product = cosine similarity apres normalisation.
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    # ----------------------------------------------------------------------
    # Sauvegarde de l'index FAISS
    # ----------------------------------------------------------------------
    faiss.write_index(
        index,
        str(INDEX_DIR / "index.faiss")
    )

    # ----------------------------------------------------------------------
    # Sauvegarde des metadonnees dans exactement le meme ordre
    # que les vecteurs FAISS.
    # ----------------------------------------------------------------------
    with open(
        INDEX_DIR / "metadata.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            chunks,
            f,
            ensure_ascii=False,
            indent=2
        )

    logger.info(
        f"Index construit : {index.ntotal} vecteurs, "
        f"dimension {dimension}"
    )
    logger.info(
        f"Sauvegarde dans {INDEX_DIR.resolve()}"
    )

    # ----------------------------------------------------------------------
    # Resume par entreprise
    # ----------------------------------------------------------------------
    from collections import Counter

    counts = Counter(
        c["entreprise"]
        for c in chunks
    )

    for entreprise, n in counts.items():
        logger.info(
            f"  {entreprise}: {n} chunks indexes"
        )

    # ----------------------------------------------------------------------
    # Resume par type de document
    # ----------------------------------------------------------------------
    type_counts = Counter(
        c["type_document"]
        for c in chunks
    )

    logger.info("")
    logger.info("Repartition par type de document:")

    for type_doc, n in type_counts.items():
        logger.info(
            f"  {type_doc}: {n} chunks"
        )

    # ----------------------------------------------------------------------
    # Audit RBAC : resume des roles presents dans l'index.
    # ----------------------------------------------------------------------
    logger.info("")
    logger.info("Repartition RBAC:")

    role_counts = Counter()

    for chunk in chunks:
        for role in chunk["allowed_roles"]:
            role_counts[role] += 1

    for role, n in sorted(role_counts.items()):
        logger.info(
            f"  {role}: {n} chunks"
        )


if __name__ == "__main__":
    build_index()