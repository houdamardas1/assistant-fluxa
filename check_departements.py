"""
Diagnostic : quels departements de l'index actuel repondent
avec des donnees REELLES (is_synthetic=False, type_document quelconque) ?
Ne modifie RIEN sur disque.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

DEPARTEMENTS = [
    "direction", "finance", "it", "rh",
    "commerce", "juridique", "marketing",
]

INDEX_DIR = Path("data/index")
METADATA_PATH = INDEX_DIR / "metadata.json"

if not METADATA_PATH.exists():
    print(f"ERREUR : {METADATA_PATH} introuvable.")
    raise SystemExit(1)

with open(METADATA_PATH, encoding="utf-8") as f:
    metadata = json.load(f)

print("=" * 72)
print(f"DIAGNOSTIC DEPARTEMENTS - {len(metadata)} chunks dans l'index")
print("=" * 72)

# --- Pour chaque departement, on compte ce qui est REELLEMENT exploitable ---
print()
print(f"{'Departement':<12} {'Total':>7} {'Reel':>7} {'Demo':>7} "
      f"{'Reglem.':>8} {'Entrepr.':>9} {'Docs':>5}  Repond ?")
print("-" * 72)

resultats = {}

for dept in DEPARTEMENTS:

    chunks = [
        c for c in metadata
        if c.get("departement") == dept
        or dept in (c.get("departements") or [])
    ]

    n_total = len(chunks)
    n_reel = sum(1 for c in chunks if not c.get("is_synthetic"))
    n_demo = sum(1 for c in chunks if c.get("is_synthetic"))
    n_regl = sum(
        1 for c in chunks
        if c.get("type_document", "entreprise") == "public_reglementaire"
    )
    n_entr = sum(
        1 for c in chunks
        if c.get("type_document", "entreprise") == "entreprise"
    )
    docs = {c.get("fichier_source") for c in chunks if c.get("fichier_source")}

    # Un departement "repond" s'il a AU MOINS 1 chunk reel non synthetique
    repond = n_reel > 0

    resultats[dept] = {
        "total": n_total,
        "reel": n_reel,
        "demo": n_demo,
        "regl": n_regl,
        "entr": n_entr,
        "docs": sorted(docs),
        "repond": repond,
    }

    statut = "OUI" if repond else "NON"
    print(f"{dept:<12} {n_total:>7} {n_reel:>7} {n_demo:>7} "
          f"{n_regl:>8} {n_entr:>9} {len(docs):>5}  {statut}")

# --- Synthese ---
print()
print("=" * 72)
print("SYNTHESE")
print("=" * 72)

prets = [d for d, r in resultats.items() if r["repond"]]
manquants = [d for d, r in resultats.items() if not r["repond"]]

print(f"Departements qui repondent AUJOURD'HUI : {len(prets)}/7")
for d in prets:
    print(f"   [OK]   {d:<12} ({resultats[d]['reel']} chunks reels, "
          f"{len(resultats[d]['docs'])} document(s))")

print()
print(f"Departements qui NE repondent PAS : {len(manquants)}/7")
for d in manquants:
    print(f"   [VIDE] {d:<12} (0 chunk)")

# --- Detail des documents par departement pret ---
print()
print("=" * 72)
print("DOCUMENTS PAR DEPARTEMENT")
print("=" * 72)

for d in DEPARTEMENTS:
    r = resultats[d]
    if not r["docs"]:
        print(f"\n[{d}] - aucun document")
        continue
    print(f"\n[{d}] - {len(r['docs'])} document(s), "
          f"{r['reel']} chunks reels")
    for doc in r["docs"]:
        # compter les chunks de ce doc
        n = sum(
            1 for c in metadata
            if (c.get("departement") == d
                or d in (c.get("departements") or []))
            and c.get("fichier_source") == doc
        )
        print(f"     - {doc}  ({n} chunks)")

# --- Chunks sans departement (orphelins) ---
print()
print("=" * 72)
print("CHUNKS SANS DEPARTEMENT (orphelins)")
print("=" * 72)

orphelins = [
    c for c in metadata
    if not c.get("departement")
    and not (c.get("departements") or [])
]

print(f"{len(orphelins)} chunks n'ont aucun tag 'departement'.")

if orphelins:
    par_fichier = Counter(c.get("fichier_source") for c in orphelins)
    print()
    print("Ces chunks viennent des fichiers suivants :")
    for fichier, n in par_fichier.most_common():
        print(f"     - {fichier}  ({n} chunks)")

print()
print("=" * 72)
print("FIN DU DIAGNOSTIC - aucune modification effectuee.")
print("=" * 72)
