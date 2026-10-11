"""Evaluation du RAG : jeu de questions de reference, indicateurs, rapports et comparaison."""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from .config import (
    GROQ_MODEL,
    GROQ_VERIFY_MODEL,
    MARGE_EMBEDDING_DEPARTEMENT,
    MODEL_NAME,
    POIDS_FAISS,
    POIDS_LEXICAL,
    ROLES_DISPONIBLES,
    SEUIL_DETECTION_DEPARTEMENT,
    SEUIL_EMBEDDING_DEPARTEMENT,
    TOP_K_CONTEXT,
    TOP_K_RETRIEVAL,
    TOP_K_VERIFY,
    VERIFY_CHARS,
)
from .pipeline import process_question_hybride
from .textutils import _norm


#
# Le jeu de donnees est un fichier JSON : une liste de cas, ou un objet
# {"cas": [...]}. Chaque cas :
#
#   {
#     "id": "wafa_ca_2025",
#     "role": "finance",                       # role simule (defaut : tous)
#     "question": "Quel est le chiffre d'affaires de Wafa Assurance en 2025 ?",
#     "expected_mode": "RAG",                  # ou liste : ["RAG", "ABSENT"]
#                                              # RAG | MULTI_INTENT | GENERAL |
#                                              # ABSENT | HORS_PERIMETRE |
#                                              # CLARIFICATION
#     "expected_source": "Wafa_Assurance_RFA_2025.pdf",   # optionnel
#     "expected_contains": ["12 738"],         # optionnel (espaces ignores)
#                                              # Un element peut etre une LISTE
#                                              # d'alternatives acceptees :
#                                              # [["12 738", "12,738"], "MDH"]
#                                              # = (12 738 OU 12,738) ET MDH
#     "expected_not_contains": ["France"],     # optionnel
#     "expected_departement": "finance",       # optionnel
#     "forcer_departement": "finance"          # optionnel (forcage explicite)
#   }
#
# Un cas est REUSSI si toutes les verifications applicables passent. Un cas
# SANS aucune attente (pas d'expected_*) est "non evalue" : il n'entre pas
# dans le taux de reussite, mais son resultat est affiche pour permettre de
# le CALIBRER (fixer ensuite expected_* a la valeur observee si elle est
# correcte, ou signaler un bug). Les
# indicateurs sont des PROXYS simples et reproductibles des metriques RAG
# classiques :
#   - retrieval_hit  : la source attendue figure dans le retrieval brut
#                      (proxy de "retrieval precision / context recall") ;
#   - contexte_hit   : la source attendue figure dans le contexte final
#                      envoye au generateur ;
#   - contenu        : la valeur attendue figure dans la reponse
#                      (proxy de "faithfulness" / exactitude) ;
#   - citations      : une reponse RAG cite au moins une source ;
#   - refus corrects / faux refus : qualite du controle d'acces.

EVAL_DIR = Path("data/eval")


def _liste(valeur) -> list:
    if valeur is None:
        return []
    return list(valeur) if isinstance(valeur, (list, tuple)) else [valeur]


def _compact(text: str) -> str:
    """Texte sans accents, en minuscules, SANS espaces (compare "12 738" et
    "12738" ou "12\u00a0738")."""
    return re.sub(r"\s+", "", _norm(text))


def _fichiers_contexte(result: dict) -> set:
    """Fichiers du contexte final (et des sources citees), y compris pour
    les questions multi-indicateurs."""
    fichiers = {r.get("fichier_source") for r in result.get("candidats_finaux", [])}
    fichiers |= {r.get("fichier_source") for _, r in result.get("cited_sources", [])}

    for sr in result.get("sous_reponses", []):
        fichiers |= _fichiers_contexte(sr["result"])

    fichiers.discard(None)
    return fichiers


def _fichiers_retrieval(result: dict) -> set:
    """Fichiers du retrieval brut (avant reclassement et garde-fous)."""
    fichiers = {r.get("fichier_source") for r in result.get("all_results", [])}

    for sr in result.get("sous_reponses", []):
        fichiers |= _fichiers_retrieval(sr["result"])

    fichiers.discard(None)
    return fichiers


def charger_jeu_evaluation(chemin) -> list:
    with open(chemin, "r", encoding="utf-8") as f:
        data = json.load(f)

    cas = data.get("cas", []) if isinstance(data, dict) else data

    if not isinstance(cas, list) or not cas:
        raise ValueError(f"Jeu d'evaluation vide ou invalide : {chemin}")

    for c in cas:
        if "question" not in c:
            raise ValueError(f"Cas sans 'question' : {c.get('id', c)}")

        if c.get("role", "tous") not in ROLES_DISPONIBLES:
            raise ValueError(f"Role inconnu dans le cas {c.get('id')}: {c.get('role')}")

    return cas


def evaluer_cas(cas: dict, model, index, metadata) -> dict:
    """Execute UN cas dans le pipeline reel et calcule ses verifications."""
    role = cas.get("role", "tous")
    attendus = _liste(cas.get("expected_mode"))

    debut = time.perf_counter()
    erreur, result = None, None

    try:
        result = process_question_hybride(
            cas["question"], model, index, metadata, role,
            selected_department=cas.get("forcer_departement"),
        )
    except Exception as e:
        erreur = f"{type(e).__name__}: {e}"

    latence = time.perf_counter() - debut

    sortie = {
        "id": cas.get("id", cas["question"][:40]),
        "role": role,
        "question": cas["question"],
        "attendus": attendus,
        "mode": None,
        "verifs": {},
        "infos": {},
        "passe": False,
        "latence_s": round(latence, 2),
        "confiance": None,
        "departement": None,
        "reponse": "",
        "erreur": erreur,
    }

    if result is None:
        return sortie

    mode = result["mode"]
    verifs, infos = {}, {}

    if attendus:
        verifs["mode"] = mode in attendus

    source = cas.get("expected_source")

    if source:
        infos["retrieval"] = source in _fichiers_retrieval(result)
        # Le contexte final n'a de sens que si le pipeline a REELLEMENT
        # produit une reponse sourcee (RAG/MULTI_INTENT). En CLARIFICATION,
        # ABSENT, GENERAL ou HORS_PERIMETRE, il n'y a pas de contexte a citer.
        if mode in ("RAG", "MULTI_INTENT"):
            verifs["contexte"] = source in _fichiers_contexte(result)

    reponse_compacte = _compact(result.get("answer", ""))

    def _present(valeur) -> bool:
        """Chaine, ou liste d'ALTERNATIVES dont une suffit."""
        return any(_compact(v) in reponse_compacte for v in _liste(valeur))

    contient = _liste(cas.get("expected_contains"))
    if contient:
        verifs["contenu"] = all(_present(c) for c in contient)

    interdit = _liste(cas.get("expected_not_contains"))
    if interdit:
        verifs["interdit"] = not any(_present(c) for c in interdit)

    if cas.get("expected_departement"):
        verifs["departement"] = result.get("departement") == cas["expected_departement"]

    if mode in ("RAG", "MULTI_INTENT") and any(
        a in ("RAG", "MULTI_INTENT") for a in attendus
    ):
        verifs["citations"] = bool(result.get("cited_sources"))

    sortie.update({
        "mode": mode,
        "verifs": verifs,
        "infos": infos,
        "passe": all(verifs.values()) if verifs else None,
        "confiance": round(result.get("confidence", 0.0), 2),
        "departement": result.get("departement"),
        "reponse": (result.get("answer") or "")[:600],
    })

    return sortie


def _taux(valeurs) -> float | None:
    valeurs = list(valeurs)
    if not valeurs:
        return None
    return round(100.0 * sum(1 for v in valeurs if v) / len(valeurs), 1)


def resumer_evaluation(resultats: list) -> dict:
    """Indicateurs agreges (pourcentages ; None = non applicable)."""
    latences = sorted(r["latence_s"] for r in resultats)
    p95 = latences[min(len(latences) - 1, int(0.95 * len(latences)))] if latences else None

    avec_refus_attendu = [r for r in resultats if "HORS_PERIMETRE" in r["attendus"]]
    sans_refus_attendu = [
        r for r in resultats if r["attendus"] and "HORS_PERIMETRE" not in r["attendus"]
    ]

    return {
        "nb_cas": len(resultats),
        "nb_erreurs": sum(1 for r in resultats if r["erreur"]),
        "nb_non_evalues": sum(
            1 for r in resultats if r["passe"] is None and not r["erreur"]
        ),
        "taux_reussite": _taux(
            r["passe"] for r in resultats if r["passe"] is not None
        ),
        "exactitude_mode": _taux(
            r["verifs"]["mode"] for r in resultats if "mode" in r["verifs"]
        ),
        "retrieval_hit": _taux(
            r["infos"]["retrieval"] for r in resultats if "retrieval" in r["infos"]
        ),
        "contexte_hit": _taux(
            r["verifs"]["contexte"] for r in resultats if "contexte" in r["verifs"]
        ),
        "exactitude_contenu": _taux(
            r["verifs"]["contenu"] for r in resultats if "contenu" in r["verifs"]
        ),
        "citations": _taux(
            r["verifs"]["citations"] for r in resultats if "citations" in r["verifs"]
        ),
        "refus_corrects": _taux(r["mode"] == "HORS_PERIMETRE" for r in avec_refus_attendu),
        "faux_refus": _taux(r["mode"] == "HORS_PERIMETRE" for r in sans_refus_attendu),
        "latence_moyenne_s": (
            round(sum(latences) / len(latences), 2) if latences else None
        ),
        "latence_p95_s": p95,
    }


_LIBELLES_RESUME = [
    ("taux_reussite", "Taux de reussite global (%)"),
    ("exactitude_mode", "Mode attendu obtenu (%)"),
    ("retrieval_hit", "Source attendue dans le retrieval (%)"),
    ("contexte_hit", "Source attendue dans le contexte final (%)"),
    ("exactitude_contenu", "Valeur attendue dans la reponse (%)"),
    ("citations", "Reponses RAG avec citation (%)"),
    ("refus_corrects", "Refus d'acces corrects (%)"),
    ("faux_refus", "Faux refus d'acces (%, plus bas = mieux)"),
    ("latence_moyenne_s", "Latence moyenne (s)"),
    ("latence_p95_s", "Latence p95 (s)"),
    ("nb_non_evalues", "Cas non evalues (a calibrer)"),
    ("nb_erreurs", "Cas en erreur"),
]


def afficher_resume_evaluation(resume: dict) -> None:
    print(f"\n{'=' * 60}\nRESUME DE L'EVALUATION ({resume['nb_cas']} cas)\n{'=' * 60}")

    for cle, libelle in _LIBELLES_RESUME:
        valeur = resume.get(cle)
        print(f"  {libelle:46s} {'n/a' if valeur is None else valeur}")

    print()


def _snapshot_configuration() -> dict:
    """Parametres qui influencent les resultats : permet d'expliquer l'ecart
    entre deux rapports (v1 vs v2)."""
    return {
        "groq_model": GROQ_MODEL,
        "groq_verify_model": GROQ_VERIFY_MODEL,
        "verify_chars": VERIFY_CHARS,
        "embedding_model": MODEL_NAME,
        "top_k_retrieval": TOP_K_RETRIEVAL,
        "top_k_verify": TOP_K_VERIFY,
        "top_k_context": TOP_K_CONTEXT,
        "poids_faiss": POIDS_FAISS,
        "poids_lexical": POIDS_LEXICAL,
        "seuil_detection_departement": SEUIL_DETECTION_DEPARTEMENT,
        "seuil_embedding_departement": SEUIL_EMBEDDING_DEPARTEMENT,
        "marge_embedding_departement": MARGE_EMBEDDING_DEPARTEMENT,
    }


def run_evaluation(
    chemin, model, index, metadata,
    label: str = "run", out_dir: Path = EVAL_DIR, pause: float = 0.0,
    ids: list | None = None,
) -> dict:
    """Rejoue tout le jeu de questions, affiche le detail et le resume, et
    sauvegarde un rapport JSON horodate (comparable via --eval-compare)."""
    cas_liste = charger_jeu_evaluation(chemin)

    if ids:
        cas_liste = [
            c for c in cas_liste
            if any(c.get("id", "").startswith(p) for p in ids)
        ]
        if not cas_liste:
            raise ValueError(f"Aucun cas ne correspond a --eval-ids {ids}")

    print(f"\nEvaluation '{label}' : {len(cas_liste)} cas depuis {chemin}\n")

    resultats = []

    for i, cas in enumerate(cas_liste, start=1):
        r = evaluer_cas(cas, model, index, metadata)
        resultats.append(r)

        echecs = [k for k, v in r["verifs"].items() if not v]

        if r["erreur"] or r["passe"] is False:
            statut = "KO"
        elif r["passe"] is None:
            statut = "--"
        else:
            statut = "OK"

        if r["erreur"]:
            detail = f"erreur={r['erreur']}"
        elif r["passe"] is None:
            detail = "non evalue (aucune attente definie)"
        else:
            detail = f"echecs={echecs}" if echecs else ""

        print(
            f"[{statut}] {i:02d}/{len(cas_liste):02d} {r['id']:32s} "
            f"role={r['role']:9s} mode={r['mode']!s:15s} "
            f"{r['latence_s']:5.1f}s {detail}"
        )

        if r["passe"] is None and not r["erreur"]:
            print(f"        reponse : {' '.join(r['reponse'].split())[:200]}")

        sys.stdout.flush()

        if r["erreur"] and r["erreur"].startswith("QuotaError"):
            print(
                "\n/!\\ Quota Groq épuisé : évaluation interrompue. "
                "Relancez après réinitialisation du quota."
            )
            break

        if pause and i < len(cas_liste):
            time.sleep(pause)

    resume = resumer_evaluation(resultats)
    afficher_resume_evaluation(resume)

    echoues = [r for r in resultats if r["passe"] is False or r["erreur"]]
    non_evalues = [r for r in resultats if r["passe"] is None and not r["erreur"]]

    if non_evalues:
        print("Cas non evalues (a calibrer : fixez expected_* avec la valeur observee) :")
        for r in non_evalues:
            print(f"  - {r['id']} : mode obtenu={r['mode']}")
        print()

    if echoues:
        print("Cas echoues (attendu -> obtenu) :")
        for r in echoues:
            print(f"  - {r['id']} : attendu={r['attendus']} obtenu={r['mode']}")
        print()

    rapport = {
        "label": label,
        "date": datetime.now().isoformat(timespec="seconds"),
        "jeu_de_donnees": str(chemin),
        "configuration": _snapshot_configuration(),
        "resume": resume,
        "cas": resultats,
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nom = f"eval_{re.sub(r'[^A-Za-z0-9_-]+', '_', label)}_{datetime.now():%Y%m%d_%H%M%S}.json"
    chemin_rapport = out_dir / nom

    with open(chemin_rapport, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    print(f"Rapport enregistre : {chemin_rapport}\n")
    return rapport


def comparer_rapports(chemin_a, chemin_b) -> None:
    """Compare deux rapports d'evaluation (A = avant, B = apres)."""
    with open(chemin_a, "r", encoding="utf-8") as f:
        a = json.load(f)
    with open(chemin_b, "r", encoding="utf-8") as f:
        b = json.load(f)

    print(f"\n{'=' * 60}")
    print(f"COMPARAISON : A='{a.get('label')}' ({a.get('date')})")
    print(f"              B='{b.get('label')}' ({b.get('date')})")
    print(f"{'=' * 60}")

    conf_a, conf_b = a.get("configuration", {}), b.get("configuration", {})
    diff_conf = {
        k: (conf_a.get(k), conf_b.get(k))
        for k in sorted(set(conf_a) | set(conf_b))
        if conf_a.get(k) != conf_b.get(k)
    }

    if diff_conf:
        print("\nParametres modifies :")
        for k, (va, vb) in diff_conf.items():
            print(f"  {k}: {va} -> {vb}")

    print(f"\n{'Indicateur':46s} {'A':>8s} {'B':>8s} {'ecart':>8s}")

    for cle, libelle in _LIBELLES_RESUME:
        va, vb = a["resume"].get(cle), b["resume"].get(cle)
        ecart = (
            f"{vb - va:+.1f}"
            if isinstance(va, (int, float)) and isinstance(vb, (int, float))
            else ""
        )
        print(
            f"{libelle:46s} {'n/a' if va is None else va:>8} "
            f"{'n/a' if vb is None else vb:>8} {ecart:>8}"
        )

    cas_a = {c["id"]: c for c in a.get("cas", [])}
    cas_b = {c["id"]: c for c in b.get("cas", [])}

    regressions = [
        i for i in cas_a
        if i in cas_b
        and cas_a[i]["passe"] is True and cas_b[i]["passe"] is False
    ]
    ameliorations = [
        i for i in cas_a
        if i in cas_b
        and cas_a[i]["passe"] is False and cas_b[i]["passe"] is True
    ]

    print(f"\nAmeliorations (KO -> OK) : {ameliorations or 'aucune'}")
    print(f"Regressions   (OK -> KO) : {regressions or 'aucune'}\n")
