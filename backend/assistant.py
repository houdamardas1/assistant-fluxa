#!/usr/bin/env python3
"""
Facade de compatibilite : expose, sous le nom `assistant`, TOUTE l'API de
l'ancien monolithe (assistant_legacy.py), maintenant repartie dans le package
`rag/`. `python assistant.py ...`, `import assistant as A` (diag_cas.py,
fusion_eval.py) et `A.<nom>` continuent donc de fonctionner a l'identique.

Pour du code neuf, importer directement depuis `rag.<module>`.
"""

import importlib

_MODULES = ("config", "llm", "textutils", "finance", "juridique", "temporel", "rbac", "departements", "messages", "retrieval", "intent", "verification", "generation", "pipeline", "diagnostics", "evaluation", "cli")

for _nom in _MODULES:
    _mod = importlib.import_module(f"rag.{_nom}")
    for _cle, _val in vars(_mod).items():
        if not _cle.startswith("__"):
            globals()[_cle] = _val

if __name__ == "__main__":
    main()
