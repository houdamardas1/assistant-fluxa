#!/usr/bin/env python3
"""
Interroge l'index FAISS en langage naturel, avec filtrage RBAC simule.
A executer depuis backend/, apres build_index.py.

Usage:
    python query_index.py
    (puis tape ta question, et choisis un role simule quand demande)
"""

import json
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

INDEX_DIR = Path("data/index")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
TOP_K = 5

ROLES_DISPONIBLES = ["tous", "finance", "direction", "it", "rh", "commerce", "juridique", "marketing"]


def load_index():
    index = faiss.read_index(str(INDEX_DIR / "index.faiss"))
    with open(INDEX_DIR / "metadata.json", "r", encoding="utf-8") as f:
        metadata = json.load(f)
    return index, metadata


def search(query: str, model, index, metadata, user_role: str, top_k: int = TOP_K):
    """Cherche les chunks les plus pertinents, puis filtre selon le role
    utilisateur simule. Elargit automatiquement la recherche si le filtrage
    RBAC laisse trop peu de resultats (ex: tous les meilleurs matchs bruts
    appartiennent a un secteur non autorise pour ce role)."""

    query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_vec)

    fetch_k = top_k * 4
    # Corpus encore petit : autant chercher dans tout l'index plutot que de
    # plafonner, sinon un departement avec peu de chunks (ex: RH, 2 chunks)
    # peut ne jamais etre trouve s'il n'est pas dans le "top 100" brut.
    max_fetch_k = index.ntotal

    while True:
        scores, indices = index.search(query_vec, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk = metadata[idx]

            # --- Filtre RBAC : le role de l'utilisateur doit etre explicitement
            # dans la liste des roles autorises du chunk. Pas de joker :
            # si l'utilisateur choisit le role "tous", il ne voit que les chunks
            # qui listent "tous" explicitement, comme n'importe quel autre role. ---
            allowed = chunk["allowed_roles"]
            if user_role not in allowed:
                continue

            results.append({
                "score": float(score),
                "entreprise": chunk["entreprise"],
                "secteur": chunk["secteur"],
                "page": chunk["page"],
                "fichier_source": chunk["fichier_source"],
                "content": chunk["content"],
                "is_synthetic": chunk.get("is_synthetic", False),
            })

            if len(results) >= top_k:
                return results

        if fetch_k >= max_fetch_k:
            return results  # on a cherche large au maximum, on rend ce qu'on a

        fetch_k = min(fetch_k * 2, max_fetch_k)


def main():
    print("Chargement de l'index...")
    index, metadata = load_index()
    print(f"{index.ntotal} chunks disponibles dans l'index.\n")

    print("Chargement du modele d'embeddings...")
    model = SentenceTransformer(MODEL_NAME)

    print(f"\nRoles disponibles pour la demo RBAC : {ROLES_DISPONIBLES}")

    while True:
        query = input("\nTa question (ou 'quit' pour sortir) : ").strip()
        if query.lower() in ("quit", "exit", ""):
            break

        role = input(f"Role simule {ROLES_DISPONIBLES} : ").strip().lower()
        if role not in ROLES_DISPONIBLES:
            print(f"Role inconnu, utilisation de 'tous' par defaut.")
            role = "tous"

        results = search(query, model, index, metadata, user_role=role)

        if not results:
            print("Aucun resultat autorise pour ce role sur cette question.")
            continue

        print(f"\n{'='*60}")
        print(f"  {len(results)} résultat(s) — rôle simulé : {role}")
        print(f"{'='*60}")
        for i, r in enumerate(results, start=1):
            tag = " [DEMO — donnée synthétique]" if r.get("is_synthetic") else ""
            print(f"\n[{i}] {r['entreprise']} ({r['secteur']}) — page {r['page']} "
                  f"— pertinence {r['score']:.3f}{tag}")
            preview = r["content"][:300].replace("\n", " ")
            print(f"    {preview}...")
        print(f"\n--- Sources ---")
        for i, r in enumerate(results, start=1):
            print(f"[{i}] {r['entreprise']} — {r['fichier_source']} — p.{r['page']}")


if __name__ == "__main__":
    main()
