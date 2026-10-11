#!/usr/bin/env python3
"""
Decoupe assistant_legacy.py (le monolithe) en package `rag/`, SANS reecrire
le code : chaque bloc de premier niveau est deplace tel quel (avec ses
commentaires). Seuls les en-tetes (docstring de module) et les imports sont
generes, a partir des noms globaux reellement utilises (module symtable).

Usage (depuis backend/) :
    python split_assistant.py [assistant_legacy.py] [dossier_sortie]

Produit :
    <sortie>/rag/*.py        les modules
    <sortie>/rag/__main__.py python -m rag
    <sortie>/assistant.py    facade de compatibilite (meme API qu'avant)

Verifier ensuite avec verifier_decoupage.py.
"""

import ast
import builtins
import re
import symtable
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Plan : module -> noms de premier niveau (dans l'ordre d'origine du fichier)
# ---------------------------------------------------------------------------

PLAN = {
    "config": [
        "<load_dotenv>", "INDEX_DIR", "MODEL_NAME", "GROQ_MODEL",
        "GROQ_VERIFY_MODEL", "TOP_K_RETRIEVAL", "TOP_K_VERIFY",
        "VERIFY_CHARS", "TOP_K_CONTEXT", "POIDS_FAISS", "POIDS_LEXICAL",
        "BONUS_ARTICLE_TITRE", "SEUIL_DETECTION_DEPARTEMENT",
        "SEUIL_EMBEDDING_DEPARTEMENT", "MARGE_EMBEDDING_DEPARTEMENT",
        "DEBUG", "ALLOW_PUBLIC_ONLY_DEPARTMENTS", "_dbg",
        "ROLES_DISPONIBLES", "DEPARTEMENTS", "LIBELLE_DEPARTEMENT",
        "RBAC_POLICY", "DEPARTMENT_ACCESS_ROLES", "ALIAS_ENTREPRISES",
        "FICHIERS_TRANSVERSES",
    ],
    "llm": ["QuotaError", "_init_groq", "groq_client", "_chat"],
    "textutils": [
        "_norm", "_regex_mots", "nettoyer_markdown", "normaliser_citations",
        "nettoyer_reponse", "STOPWORDS", "mots_utiles", "_CLASSES_ACCENTS",
        "<for_accents>", "_motif_terme", "_CACHE_MOTIFS",
        "_motif_terme_cache", "contient_terme", "position_terme",
        "contient_un_des_termes",
    ],
    "finance": [
        "FAMILLES_METIER", "detect_famille", "secteur_est_assurance",
        "termes_generiques_famille", "termes_sectoriels_famille",
        "terme_generique_present", "terme_sectoriel_present",
        "_RE_FILIALES", "_RE_DEVISES", "_RE_ASK_SOCIAL",
        "_RE_ASK_CONSOLIDE", "_TERMES_CHUNK_CONSOLIDE",
        "_TERMES_CHUNK_SOCIAL", "_SCOPE_LOCAL", "detect_scope",
        "detect_chunk_scope", "_scope_local", "scope_incompatible",
        "_PATTERNS_METRIC", "detect_metric", "metriques_presentes",
        "_normaliser_texte_preuve", "_segment_apres_metrique", "_RE_VALEUR",
        "_preuve_metric_locale", "metric_incompatible", "_LIBELLE_METRIC",
        "_LIBELLE_SCOPE", "detect_intents", "_GRAMMAIRE_METRIC",
        "_ACCORD_SCOPE", "build_subquery", "RE_MONTANT", "extraire_montant",
        "extraire_montant_source",
    ],
    "juridique": [
        "RE_REFERENCE_ARTICLE", "RE_CONTEXTE_RENVOI",
        "detect_reference_article", "est_titre_article", "est_renvoi_article",
    ],
    "temporel": [
        "TEMPORAL_PLANNED_PATTERNS", "TEMPORAL_ACTUAL_PATTERNS",
        "_report_year", "detect_temporal_requirement",
        "classify_chunk_temporal", "temporal_incompatible",
    ],
    "rbac": [
        "effective_allowed_roles", "est_accessible",
        "user_allowed_departments", "department_access_denied",
        "departements_du_chunk", "chunk_matches_department",
        "departement_a_corpus_reel", "detect_entreprises",
        "search_without_rbac", "check_rbac_restriction",
    ],
    "departements": [
        "_MOTS_CLES_DEPARTEMENT", "_RE_DEPARTEMENT", "detect_department",
        "_PHRASES_DEPARTEMENT", "_CACHE_PROTOTYPES", "_prototypes_departement",
        "detect_department_embeddings",
    ],
    "messages": [
        "MESSAGE_ABSENTE", "MESSAGE_DEPARTEMENT_VIDE",
        "MESSAGE_CLARIFICATION_PERIMETRE", "MESSAGE_QUOTA",
        "message_refus_acces",
    ],
    "retrieval": [
        "load_index", "score_lexical", "search", "_RE_CA_SOUS_PERIMETRE",
        "_RE_VALEUR_PROCHE", "select_best_candidates",
    ],
    "intent": [
        "_RE_METIER", "_RE_REGLEMENTAIRE", "_RE_INTERNE", "_RE_GOUVERNANCE",
        "PREFIXES_GENERAUX", "_INDICES_DOMAINE", "detect_intent",
        "classify_question",
    ],
    "verification": [
        "parse_json_response", "local_relevance_fallback", "_REGLES_METRIC",
        "_regles_verification", "verify_relevance",
    ],
    "generation": [
        "RE_BLOC_CROCHETS", "RE_NUMEROS_SOURCE", "extract_cited_sources",
        "_remap_source_numbers", "renumber_multi_intent_sources",
        "_contexte_departement", "_FORMAT_TEXTE_PROPRE", "_nom_source",
        "generate_general_answer", "generate_answer",
    ],
    "pipeline": [
        "_resultat", "_pipeline_rag", "process_comparative_question",
        "process_question_hybride",
    ],
    "diagnostics": [
        "audit_allowed_roles", "extended_audit_allowed_roles", "_apercu",
        "diagnostic_article", "diagnostic_terme", "diagnostic_departement",
    ],
    "evaluation": [
        "EVAL_DIR", "_liste", "_compact", "_fichiers_contexte",
        "_fichiers_retrieval", "charger_jeu_evaluation", "evaluer_cas",
        "_taux", "resumer_evaluation", "_LIBELLES_RESUME",
        "afficher_resume_evaluation", "_snapshot_configuration",
        "run_evaluation", "comparer_rapports",
    ],
    "cli": [
        "parse_args", "resolve_role", "resolve_department_override",
        "_afficher_resultat", "main",
    ],
}

DOCS = {
    "config": "Configuration : constantes, variables d'environnement, listes de roles et departements, politiques RBAC.",
    "llm": "Client Groq : initialisation, appel (_chat) et QuotaError (quota epuise != information absente).",
    "textutils": "Utilitaires texte : normalisation, nettoyage markdown, matching tolerant (accents, pluriels, tirets).",
    "finance": "Regles metier financieres : familles, perimetre social/consolide, metrique litterale, indicateurs multiples, montants.",
    "juridique": "References juridiques : detection d'un numero d'article, titre d'article ou simple renvoi.",
    "temporel": "Temporalite : annee demandee, chunk realise/prevu, incompatibilite temporelle.",
    "rbac": "Controle d'acces : roles effectifs par chunk, departements autorises, restriction RBAC, entreprises nommees.",
    "departements": "Detection automatique du departement (mots-cles puis repli par embeddings).",
    "messages": "Messages utilisateur (absence, departement vide, clarification, quota) et refus d'acces.",
    "retrieval": "Recherche hybride FAISS + lexical, rescue metier, chargement de l'index et reclassement des candidats.",
    "intent": "Classification d'intention : question d'entreprise ou generale, ENTREPRISE / GENERALE / ABSENTE.",
    "verification": "Verification de pertinence (LLM + repli local) et regles supplementaires du verificateur.",
    "generation": "Generation des reponses (RAG et generale) et gestion des citations [Source N].",
    "pipeline": "Pipeline complet : retrieval, RBAC, garde-fous, verification, generation, questions comparatives.",
    "diagnostics": "Audits RBAC et commandes de diagnostic (article, terme, departement).",
    "evaluation": "Evaluation du RAG : jeu de questions de reference, indicateurs, rapports et comparaison.",
    "cli": "Interface en ligne de commande : arguments, role, affichage et boucle interactive.",
}

IMPORTS = {
    "argparse": "import argparse",
    "json": "import json",
    "os": "import os",
    "re": "import re",
    "sys": "import sys",
    "time": "import time",
    "unicodedata": "import unicodedata",
    "Counter": "from collections import Counter",
    "datetime": "from datetime import datetime",
    "Path": "from pathlib import Path",
    "faiss": "import faiss",
    "np": "import numpy as np",
    "load_dotenv": "from dotenv import load_dotenv",
    "Groq": "from groq import Groq",
    "RateLimitError": "from groq import RateLimitError",
    "SentenceTransformer": "from sentence_transformers import SentenceTransformer",
}
EXTERNES = ("argparse", "json", "os", "re", "sys", "time", "unicodedata",
            "Counter", "datetime", "Path", "faiss", "np", "load_dotenv",
            "Groq", "RateLimitError", "SentenceTransformer")

BANNER = re.compile(r"^\s*#\s*=+\s*$")


def cle_noeud(n):
    if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
        return n.name
    if isinstance(n, ast.Assign):
        assert len(n.targets) == 1 and isinstance(n.targets[0], ast.Name), n.lineno
        return n.targets[0].id
    if isinstance(n, ast.AnnAssign):
        assert isinstance(n.target, ast.Name), n.lineno
        return n.target.id
    if isinstance(n, ast.For):
        return "<for_accents>"
    if isinstance(n, ast.Expr):
        return "<load_dotenv>"
    if isinstance(n, ast.If):
        return "<main_guard>"
    raise ValueError(f"noeud inattendu ligne {n.lineno}: {type(n).__name__}")


def debut_avec_commentaires(lignes, noeud, plancher):
    """Lignes de commentaires situees juste avant le noeud (un seul blanc
    toléré). Les bannieres '# =====' sont retirees."""
    debut = noeud.lineno - 1
    j = debut - 1
    gap = []
    if j >= plancher and lignes[j].strip() == "":
        gap = [lignes[j]]
        j -= 1
    if j < plancher or not lignes[j].lstrip().startswith("#"):
        return []
    k = j
    while k - 1 >= plancher and lignes[k - 1].lstrip().startswith("#"):
        k -= 1
    bloc = lignes[k:j + 1]
    dernier = max((i for i, l in enumerate(bloc) if BANNER.match(l)), default=-1)
    if dernier >= 0:
        bloc = bloc[dernier + 1:]
    if not bloc:
        return []
    return bloc + gap


def noms_globaux_utilises(source, definis):
    """Noms globaux references (hors builtins et hors noms definis dans le
    module), tous scopes confondus, via symtable."""
    racine = symtable.symtable(source, "<module>", "exec")
    trouves = set()

    def parcourir(table):
        for s in table.get_symbols():
            # Un nom assigne dans ce scope (ex : variable d'une comprehension
            # inlinee au niveau module) n'est pas un global importe.
            if s.is_referenced() and s.is_global() and not s.is_assigned():
                trouves.add(s.get_name())
        for enfant in table.get_children():
            parcourir(enfant)

    parcourir(racine)
    return {
        n for n in trouves
        if n not in definis and not hasattr(builtins, n)
    }


def main():
    src_path = Path(sys.argv[1] if len(sys.argv) > 1 else "assistant_legacy.py")
    sortie = Path(sys.argv[2] if len(sys.argv) > 2 else ".")
    pkg = sortie / "rag"
    pkg.mkdir(parents=True, exist_ok=True)

    source = src_path.read_text(encoding="utf-8")
    lignes = source.split("\n")
    arbre = ast.parse(source)

    # --- Affectation de chaque noeud a un module ---------------------------
    module_de = {}
    for mod, noms in PLAN.items():
        for nom in noms:
            assert nom not in module_de, f"nom affecte deux fois : {nom}"
            module_de[nom] = mod

    noeuds = []  # (noeud, cle, plancher)
    plancher = 0
    for i, n in enumerate(arbre.body):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            plancher = n.end_lineno
            continue
        if i == 0 and isinstance(n, ast.Expr) and isinstance(
            getattr(n, "value", None), ast.Constant
        ) and isinstance(n.value.value, str):
            plancher = n.end_lineno
            continue
        noeuds.append((n, cle_noeud(n), plancher))
        plancher = n.end_lineno

    cles = [c for _, c, _ in noeuds]
    assert len(cles) == len(set(cles)), "cle de noeud dupliquee"
    manquants = [c for c in cles if c != "<main_guard>" and c not in module_de]
    assert not manquants, f"noeuds non affectes : {manquants}"
    inconnus = [n for n in module_de if n not in cles]
    assert not inconnus, f"noms du plan absents du fichier : {inconnus}"

    # --- Segments de code par module ---------------------------------------
    segments = {m: [] for m in PLAN}
    for idx, (n, cle, plancher) in enumerate(noeuds):
        if cle == "<main_guard>":
            continue
        pre = debut_avec_commentaires(lignes, n, plancher)
        corps = lignes[n.lineno - 1:n.end_lineno]
        segments[module_de[cle]].append((cle, "\n".join(pre + corps)))

    # --- Generation des modules --------------------------------------------
    definis = {}
    for mod, noms in PLAN.items():
        d = set()
        for nom in noms:
            if not nom.startswith("<"):
                d.add(nom)
        # variables de boucle de niveau module
        if "<for_accents>" in noms:
            d |= {"_groupe", "_ch"}
        definis[mod] = d

    defini_dans = {}
    for mod, d in definis.items():
        for nom in d:
            defini_dans[nom] = mod

    graphe = {}

    for mod, segs in segments.items():
        corps = "\n\n\n".join(texte for _, texte in segs)
        utilises = noms_globaux_utilises(corps, definis[mod])

        externes = [n for n in EXTERNES if n in utilises]
        if mod == "config":
            externes = [n for n in EXTERNES if n in utilises or n == "load_dotenv"]

        internes = {}
        for nom in sorted(utilises):
            if nom in IMPORTS:
                continue
            if nom not in defini_dans:
                raise SystemExit(f"{mod}: nom global non resolu : {nom}")
            internes.setdefault(defini_dans[nom], []).append(nom)

        graphe[mod] = set(internes)

        entete = [f'"""{DOCS[mod]}"""', ""]
        ext = [IMPORTS[n] for n in externes]
        if ext:
            entete += ext + [""]
        for dep in sorted(internes):
            noms = internes[dep]
            if len(", ".join(noms)) < 60:
                entete.append(f"from .{dep} import {', '.join(noms)}")
            else:
                entete.append(f"from .{dep} import (")
                entete += [f"    {n}," for n in noms]
                entete.append(")")
        if internes:
            entete.append("")

        (pkg / f"{mod}.py").write_text(
            "\n".join(entete) + "\n\n" + corps + "\n", encoding="utf-8"
        )

    # --- Cycles ? ----------------------------------------------------------
    def a_cycle(g):
        etat = {}

        def visite(m, pile):
            etat[m] = 1
            for d in g.get(m, ()):
                if etat.get(d) == 1:
                    raise SystemExit(f"cycle d'imports : {' -> '.join(pile + [m, d])}")
                if d not in etat:
                    visite(d, pile + [m])
            etat[m] = 2

        for m in g:
            if m not in etat:
                visite(m, [])

    a_cycle(graphe)

    # --- __init__, __main__, facade ----------------------------------------
    (pkg / "__init__.py").write_text(
        '"""Package RAG : assistant d\'entreprise securise (RBAC, verification, citations).\n\n'
        "Modules : " + ", ".join(PLAN) + ".\n"
        'Point d\'entree : `python assistant.py ...` ou `python -m rag ...`."""\n',
        encoding="utf-8",
    )
    (pkg / "__main__.py").write_text(
        "from .cli import main\n\nmain()\n", encoding="utf-8"
    )

    garde = next(
        "\n".join(lignes[n.lineno - 1:n.end_lineno])
        for n, c, _ in noeuds if c == "<main_guard>"
    )
    modules_txt = ", ".join(f'"{m}"' for m in PLAN)
    facade = f'''#!/usr/bin/env python3
"""
Facade de compatibilite : expose, sous le nom `assistant`, TOUTE l'API de
l'ancien monolithe (assistant_legacy.py), maintenant repartie dans le package
`rag/`. `python assistant.py ...`, `import assistant as A` (diag_cas.py,
fusion_eval.py) et `A.<nom>` continuent donc de fonctionner a l'identique.

Pour du code neuf, importer directement depuis `rag.<module>`.
"""

import importlib

_MODULES = ({modules_txt})

for _nom in _MODULES:
    _mod = importlib.import_module(f"rag.{{_nom}}")
    for _cle, _val in vars(_mod).items():
        if not _cle.startswith("__"):
            globals()[_cle] = _val

{garde}
'''
    (sortie / "assistant.py").write_text(facade, encoding="utf-8")

    print(f"{len(noeuds) - 1} blocs repartis dans {len(PLAN)} modules :")
    for mod in PLAN:
        n_lignes = (pkg / f"{mod}.py").read_text(encoding="utf-8").count("\n")
        deps = ", ".join(sorted(graphe[mod])) or "-"
        print(f"  rag/{mod}.py ({n_lignes} lignes) <- {deps}")


if __name__ == "__main__":
    main()
