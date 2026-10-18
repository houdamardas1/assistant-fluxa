"""Complete les extraits coupes au saut de page dans data/index/metadata.json.

  python patch_continuations.py              simulation (n'ecrit rien)
  python patch_continuations.py --appliquer  ecrit, avec sauvegarde
                                             data/index/metadata.json.bak_continuation

Textes juridiques uniquement (type_document = public_reglementaire).
A rejouer apres toute reconstruction de l'index (comme patch_departements_v2.py).
"""

import json
import shutil
import sys
from collections import Counter

from rag.continuation import completer_extraits

P = "data/index/metadata.json"
TYPES = {"public_reglementaire"}
data = json.load(open(P, encoding="utf-8"))
liste = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
avant = [c.get("content") or "" for c in liste]
modifies = completer_extraits(liste, TYPES)
print("chunks :", len(liste), "| completes :", len(modifies))
print("par document :", dict(Counter(liste[i].get("fichier_source") for i in modifies)))
for i in modifies[:8]:
    c = liste[i]
    print("-", c.get("fichier_source"), "p.", c.get("page"))
    print("   avant :", "..." + avant[i][-70:].replace("\n", " "))
    print("   apres :", "..." + c["content"][-150:].replace("\n", " "))
if "--appliquer" in sys.argv:
    shutil.copyfile(P, P + ".bak_continuation")
    with open(P, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("OK : metadata.json mis a jour (sauvegarde .bak_continuation)")
else:
    print("(simulation : rien n'a ete ecrit ; ajouter --appliquer)")
