"""Interface en ligne de commande : arguments, role, affichage et boucle interactive."""

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from sentence_transformers import SentenceTransformer

from .config import (
    DEBUG,
    DEPARTEMENTS,
    LIBELLE_DEPARTEMENT,
    MODEL_NAME,
    ROLES_DISPONIBLES,
)
from .diagnostics import (
    audit_allowed_roles,
    diagnostic_article,
    diagnostic_departement,
    diagnostic_terme,
    extended_audit_allowed_roles,
)
from .evaluation import EVAL_DIR, comparer_rapports, run_evaluation
from .generation import _nom_source
from .llm import QuotaError
from .messages import MESSAGE_QUOTA
from .pipeline import process_question_hybride
from .retrieval import load_index


def parse_args():
    parser = argparse.ArgumentParser(
        description="Assistant RAG sécurisé (RBAC + détection automatique du département)."
    )
    parser.add_argument(
        "--role", choices=ROLES_DISPONIBLES, default=None,
        help="Rôle utilisateur (sinon RAG_USER_ROLE, sinon demandé une fois).",
    )
    parser.add_argument(
        "--departement", choices=DEPARTEMENTS, default=None,
        help="Forçage OPTIONNEL du département (sinon détection automatique).",
    )
    parser.add_argument(
        "--strict-audit", action="store_true",
        help="Quitte en erreur si un département n'a aucun document réel.",
    )
    parser.add_argument(
        "--question", default=None,
        help="Question unique en mode non interactif (Streamlit, scripts).",
    )
    parser.add_argument(
        "--eval", default=None, metavar="JEU.json",
        help="Rejoue un jeu de questions de reference et mesure la qualite.",
    )
    parser.add_argument(
        "--eval-label", default="run",
        help="Nom de l'execution d'evaluation (ex: v1, v2-chunking).",
    )
    parser.add_argument(
        "--eval-out", default=str(EVAL_DIR),
        help="Dossier des rapports d'evaluation (defaut : data/eval).",
    )
    parser.add_argument(
        "--eval-pause", type=float, default=0.0,
        help="Pause (secondes) entre deux cas, si l'API limite le debit.",
    )
    parser.add_argument(
        "--eval-ids", default=None,
        help="Prefixes d'id separes par des virgules (ex: wafa_resultat,jur_) : "
             "ne rejoue que ces cas.",
    )
    parser.add_argument(
        "--eval-compare", nargs=2, metavar=("AVANT.json", "APRES.json"),
        default=None,
        help="Compare deux rapports d'evaluation et quitte.",
    )
    return parser.parse_args()


def resolve_role(args, interactive: bool) -> str:
    """Role : argument CLI > RAG_USER_ROLE > prompt (une seule fois) > 'tous'."""
    if args.role:
        return args.role

    env_role = os.getenv("RAG_USER_ROLE", "").strip().lower()
    if env_role in ROLES_DISPONIBLES:
        return env_role

    if interactive:
        role = input(f"Rôle simulé {ROLES_DISPONIBLES} : ").strip().lower()
        if role in ROLES_DISPONIBLES:
            return role
        print("Rôle inconnu, utilisation de 'tous' par défaut.")

    return "tous"


def resolve_department_override(args) -> str | None:
    """Forçage optionnel du departement (jamais demande interactivement)."""
    if args.departement:
        return args.departement

    env_dept = os.getenv("RAG_USER_DEPARTMENT", "").strip().lower()
    return env_dept if env_dept in DEPARTEMENTS else None


def _afficher_resultat(result: dict) -> None:
    libelles = {
        "RAG": "Réponse issue des documents autorisés",
        "GENERAL": "Réponse générale",
        "ABSENT": "Information absente",
        "HORS_PERIMETRE": "Accès non autorisé",
        "MULTI_INTENT": "Comparaison multi-indicateurs",
        "CLARIFICATION": "Précision nécessaire",
    }

    print(f"\n{'=' * 60}")
    print(f"RÉPONSE - {libelles.get(result['mode'], result['mode'])}")

    if result.get("departement"):
        print(f"Département détecté : {LIBELLE_DEPARTEMENT[result['departement']]}")

    print(f"{'=' * 60}")
    print(result["answer"])

    if result["cited_sources"] or result["mode"] == "RAG":
        print(f"\n{'=' * 60}\nSOURCES UTILISÉES\n{'=' * 60}")

        if result["cited_sources"]:
            for i, r in result["cited_sources"]:
                tag = " [DEMO]" if r["is_synthetic"] else ""
                dep = f" [{r.get('departement')}]" if r.get("departement") else ""
                print(
                    f"[{i}] {_nom_source(r)} - {r['fichier_source']} - "
                    f"p.{r['page']}{dep}{tag}"
                )
        else:
            print("Aucune source explicitement citée dans la réponse.")

    if result.get("incoherence_citation"):
        print(
            "\n/!\\ Réponse sans citation : des extraits étaient disponibles "
            "mais aucune source n'a été citée. À vérifier avant diffusion."
        )

    if not DEBUG:
        return

    print(
        f"\n[Debug] Mode={result['mode']} Score={result['max_score']:.3f} "
        f"can_answer={result.get('can_answer')} "
        f"confidence={result.get('confidence', 0):.2f} "
        f"verify_error={result.get('verify_error')} "
        f"extraits={result.get('extraits_verifier')} "
        f"departement={result.get('departement')!r}"
    )

    m = result.get("montant_structure")
    if m:
        print(
            f"[Debug] Montant structuré : {m['valeur']:g} {m['unite']} "
            f"(metric={m['metric']}, scope={m['scope']})"
        )

    for sr in result.get("sous_reponses", []):
        print(
            f"[Debug] Sous-question {sr['subquery']!r} -> "
            f"can_answer={sr['result'].get('can_answer')} montant={sr['montant']}"
        )

    for titre, liste in (
        ("Classement final (envoyé au générateur)", result.get("candidats_finaux")),
        ("Retrieval brut", result.get("all_results")),
    ):
        if not liste:
            continue

        print(f"\n[Debug] {titre} :")

        for i, r in enumerate(liste[:5], start=1):
            print(
                f"  {i}. score={r['score']:.3f} "
                f"reclasse={r.get('_score_reclasse', r['score']):.3f} "
                f"(f={r['_faiss_score']:.2f} l={r['_lexical_score']:.2f}) | "
                f"{r['entreprise']} | p.{r['page']} | {r['fichier_source']}"
                f"{' | TITRE_ART' if r.get('_article_titre') else ''}"
            )


def main():
    args = parse_args()

    if args.eval_compare:
        comparer_rapports(*args.eval_compare)
        return

    print("Chargement de l'index...")
    index, metadata = load_index()
    print(f"{index.ntotal} chunks disponibles.\n")

    print("Répartition par type de document :")
    for type_doc, n in Counter(
        c.get("type_document", "ABSENT") for c in metadata
    ).items():
        print(f"   {type_doc}: {n} chunks ({(n / len(metadata)) * 100:.1f}%)")

    audit_allowed_roles(metadata)
    departements_vides = extended_audit_allowed_roles(metadata)

    if departements_vides:
        print(
            f"/!\\ ATTENTION : {len(departements_vides)} département(s) sans "
            f"document d'entreprise réel : {departements_vides}"
        )

        if args.strict_audit:
            print(
                "\n--strict-audit : arrêt. Ingérez les documents réels de ces "
                "départements (data/<dept>/) avant de relancer."
            )
            sys.exit(1)

    print("Chargement du modèle d'embeddings...")
    model = SentenceTransformer(MODEL_NAME)

    if args.eval:
        run_evaluation(
            args.eval, model, index, metadata,
            label=args.eval_label, out_dir=Path(args.eval_out),
            pause=args.eval_pause,
            ids=[p.strip() for p in args.eval_ids.split(",") if p.strip()]
            if args.eval_ids else None,
        )
        return

    interactive = sys.stdin.isatty() and not args.question
    role = resolve_role(args, interactive)
    forcage = resolve_department_override(args)

    print(f"\nRôle : {role} | Département : "
          f"{forcage or 'détection automatique'}")

    if args.question:
        try:
            result = process_question_hybride(
                args.question, model, index, metadata, role,
                selected_department=forcage,
            )
        except QuotaError:
            print(f"\n{MESSAGE_QUOTA}")
            return
        _afficher_resultat(result)
        return

    print(
        "\nCommandes :"
        "\n  diag <numero>       -> vérifie qu'un article existe dans l'index"
        "\n  terme <expression>  -> cherche un terme métier dans tout l'index"
        "\n  dept <nom>          -> diagnostic d'un département"
    )

    if not DEBUG:
        print("\n(RAG_DEBUG=1 pour afficher les détails techniques)")

    while True:
        query = input("\nVotre question (ou 'quit' pour sortir) : ").strip()

        if query.lower() in ("quit", "exit", ""):
            break

        for motif, fonction in (
            (r"diag\s+(\d+)", diagnostic_article),
            (r"terme\s+(.+)", diagnostic_terme),
            (r"dept\s+(.+)", diagnostic_departement),
        ):
            m = re.fullmatch(motif, query, flags=re.IGNORECASE)
            if m:
                fonction(metadata, m.group(1).strip())
                break
        else:
            print("\nTraitement de la question...")
            try:
                result = process_question_hybride(
                    query, model, index, metadata, role,
                    selected_department=forcage,
                )
            except QuotaError:
                print(f"\n{MESSAGE_QUOTA}")
                continue
            _afficher_resultat(result)
