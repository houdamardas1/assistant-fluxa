#!/usr/bin/env python3
"""Diagnostic d'un cas SANS appeler Groq (aucun quota consomme)."""

import argparse
import re

from sentence_transformers import SentenceTransformer

import assistant as A

LIMITE_GENERATEUR = 1500  # identique a generate_answer()


def _termes_regex(termes):
    return [(t, re.compile(re.escape(t), re.IGNORECASE)) for t in termes]


def _positions(content, termes_rx):
    out = {}
    for t, rx in termes_rx:
        m = rx.search(content or "")
        if m:
            out[t] = m.start()
    return out


def _etiquette(r):
    return f"{r.get('fichier_source')} p.{r.get('page')}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=A.ROLES_DISPONIBLES)
    ap.add_argument("--question", required=True)
    ap.add_argument("--terms", nargs="*", default=[])
    args = ap.parse_args()

    q, role = args.question, args.role
    termes_rx = _termes_regex(args.terms)

    index, metadata = A.load_index()
    model = SentenceTransformer(A.MODEL_NAME)

    print("=" * 70)
    print(f"QUESTION : {q}\nROLE     : {role}")
    print(
        f"CONFIG   : verify_model={A.GROQ_VERIFY_MODEL} "
        f"top_k_verify={A.TOP_K_VERIFY} verify_chars={A.VERIFY_CHARS}"
    )
    print("=" * 70)

    dept = A.detect_department(q, role)
    origine = "mots-cles"
    if dept is None:
        dept = A.detect_department_embeddings(q, model, role)
        origine = "embeddings"
        if A.department_access_denied(role, dept):
            dept = None

    filtre = dept if dept and A.departement_a_corpus_reel(metadata, dept) else None
    print(f"\nDepartement detecte : {dept!r} ({origine}) | filtre applique : {filtre!r}")

    if termes_rx:
        print("\n[1] Chunks de l'INDEX (accessibles a ce role) contenant les termes :")
        for t, rx in termes_rx:
            acces = [
                c for c in metadata
                if A.est_accessible(c, role) and rx.search(c.get("content", ""))
            ]
            print(f"  - '{t}' : {len(acces)} chunk(s) accessible(s)")
            for c in acces[:6]:
                pos = rx.search(c["content"]).start()
                print(
                    f"      {c.get('fichier_source')} p.{c.get('page')} "
                    f"position={pos} longueur={len(c['content'])}"
                )

    results = A.search(
        q, model, index, metadata, user_role=role,
        top_k=A.TOP_K_RETRIEVAL, selected_department=filtre,
    )
    print(f"\n[2] Retrieval brut : {len(results)} resultat(s)")

    if termes_rx:
        trouve = False
        for rang, r in enumerate(results, start=1):
            pos = _positions(r.get("content", ""), termes_rx)
            if pos:
                trouve = True
                print(f"  rang {rang:2d} : {_etiquette(r)} score={r['score']:.3f} termes={pos}")
        if not trouve:
            print("  /!\\ AUCUN chunk contenant les termes n'est dans le retrieval brut.")

    restreint = A.check_rbac_restriction(q, model, index, metadata, role, results)
    print(f"\n[3] check_rbac_restriction : {restreint}")

    candidats = A.select_best_candidates(q, results, top_n=A.TOP_K_VERIFY)
    print(f"\n[4] Candidats apres reclassement : {len(candidats)}")

    for i, r in enumerate(candidats, start=1):
        pos = _positions(r.get("content", ""), termes_rx)
        marque = f" <-- termes {pos}" if pos else ""
        print(
            f"  {i:2d}. {_etiquette(r)} reclasse={r.get('_score_reclasse', 0):.3f} "
            f"scope={r.get('_scope')} preuve_metric={r.get('_preuve_metric')}{marque}"
        )

    if termes_rx:
        dans = [
            i for i, r in enumerate(candidats, start=1)
            if _positions(r.get("content", ""), termes_rx)
        ]
        if not dans:
            print("  /!\\ Aucun candidat ne contient les termes : perdu au RECLASSEMENT/selection.")

    print("\n[5] Garde-fous deterministes :")
    restants = []
    for i, r in enumerate(candidats, start=1):
        c = r.get("content", "")
        motifs = []
        if A.scope_incompatible(q, c):
            motifs.append("scope")
        if A.metric_incompatible(q, c):
            motifs.append("metrique")
        if A.temporal_incompatible(q, r):
            motifs.append("temporalite")

        pos = _positions(c, termes_rx)
        if motifs:
            marque = " <-- CHUNK UTILE ELIMINE" if pos else ""
            print(f"  {i:2d}. ELIMINE par {motifs} : {_etiquette(r)}{marque}")
        else:
            restants.append(r)

    print(f"  => {len(restants)} candidat(s) restant(s) sur {len(candidats)}")

    print(
        f"\n[6] Vue du VERIFICATEUR (extraits[:{A.VERIFY_CHARS}], "
        f"{A.TOP_K_VERIFY} max) :"
    )
    for n, r in enumerate(restants[:A.TOP_K_VERIFY], start=1):
        c = r.get("content", "")
        pos = _positions(c, termes_rx)
        etat = ""
        if termes_rx:
            if not pos:
                etat = "(termes absents du chunk)"
            else:
                coupes = {t: p for t, p in pos.items() if p >= A.VERIFY_CHARS}
                visibles = {t: p for t, p in pos.items() if p < A.VERIFY_CHARS}
                if visibles:
                    etat += f" visibles={visibles}"
                if coupes:
                    etat += f" /!\\ COUPES par la troncature verificateur={coupes}"
                coupes_g = {t: p for t, p in pos.items() if p >= LIMITE_GENERATEUR}
                if coupes_g:
                    etat += f" /!\\ COUPES pour le generateur ({LIMITE_GENERATEUR})={coupes_g}"
        print(f"  Extrait {n:2d} : {_etiquette(r)} longueur={len(c)} {etat}")


if __name__ == "__main__":
    main()
