#!/usr/bin/env python3
"""Rattache a 'finance' ET 'direction' les chunks de rapports d'entreprise etiquetes
'finance' seul OU 'direction' seul (symetrique).

Pourquoi : « Qui compose le conseil de Wafa ? » est routee vers 'direction' alors que les
chunks Wafa ne sont etiquetes que 'finance' ; « CA d'Unimer ? » est routee vers 'finance'
alors que les chunks Unimer ne sont etiquetes que 'direction'. Le filtre les exclut AVANT
la recherche. Convention historique du code (chunk_matches_department) :
un chunk d'entreprise est rattache a Finance ET Direction.

- Ne touche PAS au controle d'acces (access_roles / allowed_roles inchanges).
- Ne touche PAS a l'index FAISS (seul metadata.json change, meme ordre, memes chunks).
- Simulation par defaut ; --apply ecrit apres sauvegarde horodatee.

Usage (depuis backend/) :
  python patch_departements.py            # simulation : affiche ce qui changerait
  python patch_departements.py --apply    # applique (sauvegarde metadata.json.bak_...)
"""
import argparse, json, shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

CHEMIN = Path("data/index/metadata.json")


def a_changer(c):
    deps = c.get("departements")
    if isinstance(deps, list) and deps:
        return False                      # deja classe en multi-departements
    return (c.get("type_document", "entreprise") == "entreprise"
            and c.get("departement") in ("finance", "direction"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    m = json.load(open(CHEMIN, encoding="utf-8"))
    avant = Counter((c.get("entreprise"), c.get("departement"), tuple(c.get("departements") or ())) for c in m)
    cibles = [c for c in m if a_changer(c)]

    print(f"{len(m)} chunks dans l'index ; {len(cibles)} a rattacher a finance + direction :")
    for (ent, dep, deps), n in sorted(avant.items(), key=lambda x: -x[1]):
        marque = "  <-- modifie" if dep in ("finance", "direction") and not deps and any(
            a_changer(c) and c.get("entreprise") == ent for c in m) else ""
        print(f"  {str(ent):18s} departement={dep!s:10s} departements={list(deps)!s:20s} x{n}{marque}")

    if not a.apply:
        print("\nSimulation uniquement. Relance avec --apply pour ecrire.")
        return
    if not cibles:
        print("Rien a faire.")
        return

    sauvegarde = CHEMIN.with_name(f"metadata.json.bak_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(CHEMIN, sauvegarde)
    for c in cibles:
        c["departements"] = ["finance", "direction"]
    with open(CHEMIN, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False)
    print(f"\nAppliquee : {len(cibles)} chunks. Sauvegarde : {sauvegarde.name}")
    print("Redemarre l'API (l'index est charge au demarrage).")


if __name__ == "__main__":
    main()
