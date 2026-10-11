"""
Corrige les chunks public_reglementaire qui portent encore une
'entreprise' (residu d'un ancien pipeline). Un texte de loi n'appartient
a aucune entreprise : on met entreprise=None.

Ne touche QUE les chunks type_document == "public_reglementaire".
"""
import json
from pathlib import Path

INDEX_DIR = Path("data/index")

with open(INDEX_DIR / "metadata.json", encoding="utf-8") as f:
    metadata = json.load(f)

n_corriges = 0
for chunk in metadata:
    if chunk.get("type_document") == "public_reglementaire":
        if chunk.get("entreprise") is not None:
            chunk["entreprise"] = None
            n_corriges += 1

print(f"{n_corriges} chunk(s) public_reglementaire corriges (entreprise=None)")

if n_corriges > 0:
    backup = INDEX_DIR / "backups"
    backup.mkdir(exist_ok=True)
    with open(INDEX_DIR / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print("metadata.json mis a jour.")
else:
    print("Rien a corriger.")
