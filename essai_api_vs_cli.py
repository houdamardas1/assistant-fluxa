#!/usr/bin/env python3
"""Compare, DANS LE MEME PROCESSUS, le chemin de l'API (RagService.ask) et celui de la
ligne de commande (assistant.process_question_hybride). Meme modele, meme index, meme role.

Si les verdicts alternent : le verificateur LLM est instable (cause commune).
Si l'un des deux est toujours different de l'autre : il y a une vraie difference de chemin.

Usage (depuis backend/, API arretee pour ne pas doubler la charge) :
  python essai_api_vs_cli.py
Consomme environ 6 appels au verificateur Groq (pause de 15 s entre chaque).
"""
import os
os.environ["RAG_DEBUG"] = "1"          # avant l'import de rag.config

import time

import assistant as A
from app.services.rag_service import RagService

QUESTION = "Quel est le résultat net de CDG Capital en 2024 ?"
ROLE = "direction"

svc = RagService.from_disk()
bilan = []

for i in range(1, 4):
    for nom in ("API", "CLI"):
        print(f"\n######## essai {i} - chemin {nom} ########", flush=True)
        if nom == "API":
            r = svc.ask(QUESTION, ROLE)
        else:
            r = A.process_question_hybride(
                QUESTION, svc.model, svc.index, svc.metadata, ROLE,
                selected_department=None,
            )
        ligne = f"{nom} essai {i} : mode={r['mode']} can_answer={r.get('can_answer')} | {r['answer'][:70]!r}"
        bilan.append(ligne)
        print(ligne, flush=True)
        time.sleep(15)

print("\n================ BILAN ================")
print("\n".join(bilan))
