#!/usr/bin/env python3
"""Fusionne plusieurs rapports d'evaluation partiels en une seule reference.

Usage (depuis backend/) :
  python fusion_eval.py data\\eval\\eval_v4_*.json data\\eval\\eval_v4-acces_*.json ...
Les cas en erreur (quota) sont ignores ; en cas de doublon, le rapport le
plus recent (dans l'ordre des arguments) l'emporte.
"""
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

import assistant as A

JEU = "data/eval/v1.json"


def main():
    chemins = []
    for arg in sys.argv[1:]:
        chemins += sorted(glob.glob(arg)) or [arg]

    if not chemins:
        print(__doc__)
        return

    cas, configs = {}, {}

    for p in chemins:
        with open(p, "r", encoding="utf-8") as f:
            rapport = json.load(f)

        conf = rapport.get("configuration", {})
        configs[p] = (
            conf.get("groq_model"), conf.get("groq_verify_model"),
            conf.get("top_k_verify"), conf.get("verify_chars"),
        )

        for c in rapport.get("cas", []):
            if c.get("erreur"):
                continue
            cas[c["id"]] = c

    if len(set(configs.values())) > 1:
        print("/!\\ Les rapports n'ont pas la meme configuration "
              "(modele, verificateur, top_k_verify, verify_chars) :")
        for p, c in configs.items():
            print(f"    {Path(p).name} : {c}")
        print()

    ordre = [c["id"] for c in A.charger_jeu_evaluation(JEU) if "id" in c]
    resultats = [cas[i] for i in ordre if i in cas]
    manquants = [i for i in ordre if i not in cas]

    print(f"Cas fusionnes : {len(resultats)}/{len(ordre)}")
    if manquants:
        print(f"Cas encore manquants ({len(manquants)}) : {manquants}")

    resume = A.resumer_evaluation(resultats)
    A.afficher_resume_evaluation(resume)

    echoues = [r for r in resultats if r["passe"] is False]
    if echoues:
        print("Cas echoues (attendu -> obtenu) :")
        for r in echoues:
            print(f"  - {r['id']} : attendu={r['attendus']} obtenu={r['mode']}")
        print()

    rapport = {
        "label": "v4-fusion",
        "date": datetime.now().isoformat(timespec="seconds"),
        "jeu_de_donnees": JEU,
        "configuration": A._snapshot_configuration(),
        "complet": not manquants,
        "sources": [str(Path(p).name) for p in chemins],
        "resume": resume,
        "cas": resultats,
    }

    sortie = Path("data/eval") / f"eval_v4-fusion_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    print(f"Rapport fusionne : {sortie}"
          + ("" if not manquants else "  (INCOMPLET : ne pas utiliser comme reference)"))


if __name__ == "__main__":
    main()