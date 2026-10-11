#!/usr/bin/env python3
"""
Prouve que le package rag/ est le MEME code que le monolithe, redistribue.

Usage (depuis backend/) :
    python verifier_decoupage.py [assistant_legacy.py] [dossier_contenant_rag_et_assistant.py]

Controles (aucun appel Groq, aucun index requis) :
  1. ARBRE SYNTAXIQUE : chaque bloc de premier niveau du monolithe (fonction,
     classe, constante, boucle...) se retrouve a l'identique (ast.dump) dans
     un module de rag/ ; aucun bloc en trop, aucun manquant ;
  2. COMMENTAIRES : aucun commentaire perdu ni ajoute (hors bannieres) ;
  3. NOMS GLOBAUX : aucun nom utilise sans etre defini ou importe dans son
     module (detecte les NameError a l'execution) ;
  4. CYCLES : aucun cycle d'imports entre modules ;
  5. API : la facade assistant.py expose tous les noms de l'ancien monolithe.

Code de sortie 0 si tout est conforme, 1 sinon.
"""

import ast
import builtins
import io
import re
import sys
import symtable
import tokenize
from collections import Counter
from pathlib import Path

BANNER = re.compile(r"^#\s*=+\s*$")


def noeuds_premier_niveau(source):
    """Liste de (cle, dump) des blocs de premier niveau, hors imports et
    docstring de module."""
    arbre = ast.parse(source)
    res = []
    for i, n in enumerate(arbre.body):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            continue
        if (
            i == 0 and isinstance(n, ast.Expr)
            and isinstance(getattr(n, "value", None), ast.Constant)
            and isinstance(n.value.value, str)
        ):
            continue
        res.append(ast.dump(n))
    return res


def commentaires(source):
    """Commentaires hors shebang et hors bannieres de section (ligne
    '# ====', titre, ligne '# ====' : remplacees par la docstring du module)."""
    jetons = [
        (t.start[0], t.string.strip())
        for t in tokenize.generate_tokens(io.StringIO(source).readline)
        if t.type == tokenize.COMMENT
    ]
    par_ligne = dict(jetons)
    out = Counter()
    for ligne, c in jetons:
        if c.startswith("#!") or BANNER.match(c):
            continue
        if BANNER.match(par_ligne.get(ligne - 1, "")) and BANNER.match(
            par_ligne.get(ligne + 1, "")
        ):
            continue  # titre de banniere
        out[c] += 1
    return out


def noms_definis(arbre):
    d = set()
    for n in ast.walk(arbre):
        pass
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            d.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                d.add((a.asname or a.name).split(".")[0])
        else:
            for sub in ast.walk(n):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    # cibles de niveau module (y compris variables de boucle)
                    d.add(sub.id)
    return d


def globaux_non_resolus(source):
    arbre = ast.parse(source)
    definis = noms_definis(arbre)
    racine = symtable.symtable(source, "<module>", "exec")
    manque = set()

    def parcourir(table):
        for s in table.get_symbols():
            if s.is_referenced() and s.is_global() and not s.is_assigned():
                n = s.get_name()
                if n not in definis and not hasattr(builtins, n):
                    manque.add(n)
        for e in table.get_children():
            parcourir(e)

    parcourir(racine)
    return manque


def cycle(graphe):
    etat = {}

    def visite(m, pile):
        etat[m] = 1
        for d in graphe.get(m, ()):
            if etat.get(d) == 1:
                return pile + [m, d]
            if d not in etat:
                r = visite(d, pile + [m])
                if r:
                    return r
        etat[m] = 2
        return None

    for m in graphe:
        if m not in etat:
            r = visite(m, [])
            if r:
                return r
    return None


def main():
    legacy = Path(sys.argv[1] if len(sys.argv) > 1 else "assistant_legacy.py")
    racine = Path(sys.argv[2] if len(sys.argv) > 2 else ".")
    pkg = racine / "rag"
    facade = racine / "assistant.py"

    ok = True

    def verdict(nom, bon, detail=""):
        nonlocal ok
        ok = ok and bon
        print(f"[{'OK' if bon else 'KO'}] {nom}" + (f" : {detail}" if detail else ""))

    src_legacy = legacy.read_text(encoding="utf-8")
    modules = sorted(p for p in pkg.glob("*.py") if p.stem not in ("__init__", "__main__"))
    sources = {p.stem: p.read_text(encoding="utf-8") for p in modules}

    # 1. Arbres syntaxiques --------------------------------------------------
    attendus = Counter(noeuds_premier_niveau(src_legacy))
    obtenus = Counter()
    for s in sources.values():
        obtenus.update(noeuds_premier_niveau(s))
    # la garde `if __name__ == "__main__"` vit dans la facade
    arbre_f = ast.parse(facade.read_text(encoding="utf-8"))
    for n in arbre_f.body:
        if isinstance(n, ast.If):
            obtenus[ast.dump(n)] += 1

    manquants = attendus - obtenus
    en_trop = obtenus - attendus
    verdict(
        "1. Code identique (arbres syntaxiques)",
        not manquants and not en_trop,
        f"{sum(attendus.values())} blocs du monolithe retrouves a l'identique"
        if not manquants and not en_trop
        else f"{sum(manquants.values())} manquant(s), {sum(en_trop.values())} en trop",
    )

    # 2. Commentaires --------------------------------------------------------
    c_old = commentaires(src_legacy)
    c_new = Counter()
    for s in list(sources.values()) + [facade.read_text(encoding="utf-8")]:
        c_new.update(commentaires(s))
    perdus = c_old - c_new
    ajoutes = c_new - c_old
    verdict(
        "2. Commentaires conserves",
        not perdus and not ajoutes,
        f"{sum(c_old.values())} commentaires" if not perdus and not ajoutes
        else f"perdus={sum(perdus.values())} ajoutes={sum(ajoutes.values())}",
    )
    for c in list(perdus)[:5]:
        print(f"      perdu : {c[:80]}")

    # 3. Noms globaux --------------------------------------------------------
    problemes = {m: globaux_non_resolus(s) for m, s in sources.items()}
    problemes = {m: n for m, n in problemes.items() if n}
    verdict(
        "3. Aucun nom global non resolu",
        not problemes,
        "" if not problemes else str({m: sorted(n) for m, n in problemes.items()}),
    )

    # 4. Cycles ---------------------------------------------------------------
    graphe = {}
    for m, s in sources.items():
        deps = set()
        for n in ast.parse(s).body:
            if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module:
                deps.add(n.module)
        graphe[m] = deps
    c = cycle(graphe)
    verdict("4. Aucun cycle d'imports", c is None, "" if c is None else " -> ".join(c))

    # 5. API ------------------------------------------------------------------
    attendus_api = set()
    for n in ast.parse(src_legacy).body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            attendus_api.add(n.name)
        elif isinstance(n, ast.Assign):
            attendus_api.update(t.id for t in n.targets if isinstance(t, ast.Name))
        elif isinstance(n, ast.AnnAssign):
            attendus_api.add(n.target.id)
    exposes = set()
    for s in sources.values():
        for n in ast.parse(s).body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                exposes.add(n.name)
            elif isinstance(n, ast.Assign):
                exposes.update(t.id for t in n.targets if isinstance(t, ast.Name))
            elif isinstance(n, ast.AnnAssign):
                exposes.add(n.target.id)
    absents = attendus_api - exposes
    verdict(
        "5. API de l'ancien monolithe presente",
        not absents,
        f"{len(attendus_api)} noms" if not absents else f"absents : {sorted(absents)}",
    )

    print("\nRESULTAT :", "CONFORME" if ok else "NON CONFORME")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
