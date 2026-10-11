#!/usr/bin/env python3
"""
Test RBAC systématique
Vérifie que les filtres de rôle fonctionnent correctement
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

INDEX_DIR = Path("data/index")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
TOP_K = 10

TEST_SUITE = {
    "finance": [
        "Quel est le chiffre d'affaires de Wafa Assurance",
        "Quel est le résultat net de CDG Capital",
        "Quel est le chiffre d'affaires d'Unimer",
        "Quel est le résultat net de Auto Nejma",
        "Quel est le bénéfice de Wafa Assurance",
        "Quelle est la marge de CDG Capital",
        "Quel est le CA d'Unimer",
        "Quel est le résultat de Auto Nejma",
    ],
    "direction": [
        "Quel est le chiffre d'affaires de Wafa Assurance",
        "Quel est le résultat net de CDG Capital",
        "Quel est le chiffre d'affaires d'Unimer",
        "Quel est le résultat net de Auto Nejma",
        "Quelle est la situation financière de Wafa Assurance",
        "Quels sont les indicateurs clés de CDG Capital",
        "Quelle est la performance d'Unimer",
        "Quel est le bilan de Auto Nejma",
    ],
    "tous": [
        "Quel est le chiffre d'affaires de Wafa Assurance",
        "Quel est le résultat net de CDG Capital",
        "Quel est le chiffre d'affaires d'Unimer",
        "Quel est le résultat net de Auto Nejma",
    ]
}


def load_index():
    index = faiss.read_index(str(INDEX_DIR / "index.faiss"))
    with open(INDEX_DIR / "metadata.json", "r", encoding="utf-8") as f:
        metadata = json.load(f)
    return index, metadata


def search(query: str, model, index, metadata, user_role: str) -> List[Dict]:
    query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_vec)

    fetch_k = min(index.ntotal, TOP_K * 10)
    scores, indices = index.search(query_vec, fetch_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        chunk = metadata[idx]

        allowed = chunk["allowed_roles"]
        if user_role not in allowed:
            continue

        results.append({
            "score": float(score),
            "entreprise": chunk.get("entreprise", "Inconnu"),
            "secteur": chunk.get("secteur", "Inconnu"),
            "page": chunk.get("page", 0),
            "fichier_source": chunk.get("fichier_source", ""),
            "content": chunk.get("content", "")[:200],
            "allowed_roles": allowed
        })

        if len(results) >= TOP_K:
            return results

    return results


def test_role(model, index, metadata, role: str) -> Dict[str, Any]:
    results = {}
    queries = TEST_SUITE.get(role, [])

    print(f"\nTest du role: {role.upper()}")
    print("-" * 50)

    for query in queries:
        print(f"\nQuestion: {query}")
        docs = search(query, model, index, metadata, user_role=role)

        if docs:
            entreprises_trouvees = set()
            for doc in docs:
                entreprises_trouvees.add(doc["entreprise"])

            print(f"   {len(docs)} resultats trouves")
            print(f"   Entreprises: {', '.join(entreprises_trouvees)}")

            first = docs[0]
            print(f"   Meilleur resultat: {first['entreprise']} (page {first['page']}) - score: {first['score']:.3f}")
            print(f"   Extrait: {first['content'][:100]}...")

            results[query] = {
                "status": "success",
                "count": len(docs),
                "entreprises": list(entreprises_trouvees),
                "best_score": first["score"],
                "best_entreprise": first["entreprise"],
                "best_page": first["page"]
            }
        else:
            print(f"   Aucun resultat trouve")
            results[query] = {
                "status": "failed",
                "count": 0,
                "entreprises": []
            }

    return results


def generate_report(all_results: Dict) -> str:
    report = "\n" + "="*70 + "\n"
    report += "RAPPORT DE TEST RBAC\n"
    report += "="*70 + "\n"

    report += "\nMATRICE DES RESULTATS\n"
    report += "-"*70 + "\n"
    report += f"{'Question':<50} {'Finance':<10} {'Direction':<10} {'Tous':<10}\n"
    report += "-"*70 + "\n"

    all_questions = set()
    for role_queries in TEST_SUITE.values():
        all_questions.update(role_queries)

    for question in sorted(all_questions):
        line = f"{question[:48]:<50}"
        for role in ["finance", "direction", "tous"]:
            if question in TEST_SUITE.get(role, []):
                role_results = all_results.get(role, {})
                if role_results.get(question, {}).get("status") == "success":
                    line += f"{'OK':<10}"
                else:
                    line += f"{'X':<10}"
            else:
                line += f"{'-':<10}"
        report += line + "\n"

    report += "\nSTATISTIQUES\n"
    report += "-"*70 + "\n"

    for role in ["finance", "direction", "tous"]:
        role_results = all_results.get(role, {})
        total = len(role_results)
        success = sum(1 for r in role_results.values() if r.get("status") == "success")
        if total > 0:
            report += f"   {role.upper():<12} {success}/{total} reussis ({success/total*100:.1f}%)\n"
        else:
            report += f"   {role.upper():<12} 0/0 (N/A)\n"

    report += "\n" + "="*70 + "\n"

    return report


def main():
    print("TEST RBAC SYSTEMATIQUE")
    print("=" * 50)

    print("\nChargement de l'index...")
    index, metadata = load_index()
    print(f"{index.ntotal} chunks disponibles")

    print("\nChargement du modele d'embeddings...")
    model = SentenceTransformer(MODEL_NAME)
    print("Modele charge")

    all_results = {}
    for role in ["finance", "direction", "tous"]:
        all_results[role] = test_role(model, index, metadata, role)

    report = generate_report(all_results)
    print(report)

    report_file = Path("data/test_rbac_report.txt")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Rapport sauvegarde: {report_file}")

    json_file = Path("data/test_rbac_results.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"Resultats detailles: {json_file}")


if __name__ == "__main__":
    main()
