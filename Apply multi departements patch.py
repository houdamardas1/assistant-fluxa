#!/usr/bin/env python3
"""
Applique la lecture du champ "departements" a VOS fichiers assistant.py et
ingest_departements.py.

Principe (deux concepts INDEPENDANTS) :

    departements  ->  pertinence du chunk pour l'ONGLET selectionne
    RBAC          ->  droit reel de LECTURE (RBAC_POLICY, access_roles,
                      DEPARTMENT_ACCESS_ROLES, allowed_roles)

Ce patch ne touche PAS au RBAC : effective_allowed_roles() n'est pas modifiee
et ne lit jamais "departements". Le champ "departements" est calcule hors
ligne par classify_enterprise_departments.py ; assistant.py se contente de le
LIRE pour filtrer le perimetre de l'onglet.

    classify_enterprise_departments.py -> metadata.json -> assistant.py
    (classification offline)                              (filtre onglet + RBAC existant)

Usage (depuis le dossier qui contient vos fichiers) :

    python apply_multi_departements_patch.py --dry-run     # verifie les ancrages
    python apply_multi_departements_patch.py               # applique

Chaque remplacement est ancre sur le code exact (arret sans rien ecrire si un
ancrage est introuvable ou ambigu) ; le resultat est verifie (compilation) ;
l'original est conserve en *.bak_multi_dept (jamais ecrase). Idempotent.

assistant.py
  1. departements_du_chunk() : lit "departements" puis "departement".
  2. chunk_matches_department() : filtre de perimetre multi-departements.
  3. extended_audit_allowed_roles() et diagnostic_departement() : comptent le
     champ multi (affichage uniquement).
  4. search() : expose "departements" dans les resultats (affichage/debug).
  5. search_without_rbac() : transporte access_roles et departement pour que
     check_rbac_restriction() -> effective_allowed_roles(r) calcule les MEMES
     droits que sur le chunk d'origine (correction d'un faux HORS_PERIMETRE
     deja possible aujourd'hui pour les chunks ingeres par departement).
     Aucun droit n'est modifie.

ingest_departements.py
  1. retag_existing() ne touche jamais un chunk deja classe "departements".
  2. afficher_audit_departements() compte aussi le champ multi.
"""

import argparse
import ast
import re
import sys
from pathlib import Path

MARQUEUR = "def departements_du_chunk("


class PatchError(Exception):
    pass


def unique(texte, ancien, nouveau, nom):
    n = texte.count(ancien)
    if n != 1:
        raise PatchError(f"[{nom}] ancrage trouve {n} fois (attendu : 1).")
    return texte.replace(ancien, nouveau)


def regex_unique(texte, motif, nouveau, nom):
    rx = re.compile(motif, flags=re.S)
    n = len(rx.findall(texte))
    if n != 1:
        raise PatchError(f"[{nom}] motif trouve {n} fois (attendu : 1).")
    return rx.sub(lambda _m: nouveau, texte, count=1)


DOC_41 = '''correspondent a DEPARTMENT_ACCESS_ROLES.
 40. extended_audit_allowed_roles() ne masque plus les chunks
     reglementaires deja tagges par departement (voir ingest_
     departements.py --retag-existing).
 41. LECTURE DE LA CLASSIFICATION MULTI-DEPARTEMENTS : un chunk d'entreprise
     reel peut porter "departements": ["it", "direction"], calcule HORS
     LIGNE a partir de son contenu par classify_enterprise_departments.py
     (aucune donnee fabriquee). Deux concepts restent independants :
       - "departements" : ce chunk est-il PERTINENT pour l'onglet ?
         (departements_du_chunk, chunk_matches_department) ;
       - RBAC : ce role a-t-il le DROIT de le lire ?
         (effective_allowed_roles, qui ne lit JAMAIS "departements").
     Les chunks non classifies gardent la regle historique (visibles
     sous Finance/Direction).
"""'''

HELPER_ET_FONCTION = '''def departements_du_chunk(chunk: dict) -> set:
    """
    Departements auxquels un chunk est rattache (perimetre d'onglet).

    Priorite : "departements" (liste, classification multi-departements)
    puis "departement" (ancien champ mono-departement). Ensemble vide si
    le chunk n'est classe dans aucun departement connu.

    NE SERT PAS au controle d'acces : effective_allowed_roles() ne lit
    jamais ce champ.
    """
    deps = chunk.get("departements")

    if isinstance(deps, list) and deps:
        valides = {d for d in deps if d in DEPARTEMENTS}
        if valides:
            return valides

    dep = chunk.get("departement")

    return {dep} if dep in DEPARTEMENTS else set()


def chunk_matches_department(chunk: dict, selected_department: str) -> bool:
    """
    Vrai si `chunk` appartient au perimetre du departement selectionne
    dans l'UI.

    Ce n'est PAS un controle d'acces (est_accessible()/
    effective_allowed_roles() restent l'unique source de verite pour la
    securite, et sont appliques independamment, avant ce filtre) : c'est
    un filtre de PERIMETRE, comme `entreprises_visees` dans search().

    Priorite :
      1. documents reglementaires publics : visibles sous tous les onglets ;
      2. "departements" (multi) ou ancien "departement" : correspondance
         directe ;
      3. compatibilite historique : chunk d'entreprise NON encore
         classifie -> rattache par convention a Finance et Direction.
    """

    if chunk.get("type_document", "entreprise") == "public_reglementaire":
        return True

    deps = departements_du_chunk(chunk)

    if deps:
        return selected_department in deps

    if selected_department in ("finance", "direction"):
        return chunk.get("type_document", "entreprise") == "entreprise"

    return False


'''

BLOC_AUDIT = '''for dept in departements_du_chunk(chunk):
            chunks_par_departement[dept].append(chunk)

        if (
            not departements_du_chunk(chunk)
            and chunk.get("type_document", "entreprise") != "public_reglementaire"
            and chunk.get("entreprise") not in RBAC_POLICY
        ):
            chunks_orphelins.append(chunk)'''


def patcher_assistant(t):
    if MARQUEUR in t:
        raise PatchError("assistant.py deja a jour (rien a faire).")

    t = unique(t, 'correspondent a DEPARTMENT_ACCESS_ROLES.\n"""', DOC_41, "docstring")

    t = regex_unique(
        t,
        r"def chunk_matches_department\(.*?(?=# =+\n# Detection d'entreprise)",
        HELPER_ET_FONCTION,
        "chunk_matches_department",
    )

    t = regex_unique(
        t,
        r'dept = chunk\.get\("departement"\)\s+if dept in chunks_par_departement:.*?chunks_orphelins\.append\(chunk\)',
        BLOC_AUDIT,
        "extended_audit (regroupement)",
    )

    t = unique(
        t,
        'print("\\nAudit RBAC EFFECTIF par DEPARTEMENT (correction 39/40) :")',
        'print("\\nAudit RBAC EFFECTIF par DEPARTEMENT (correction 39/40/41) :")\n'
        '    print("   (un chunk multi-departements compte dans chacun de ses "\n'
        '          "departements : la somme peut depasser le total)")',
        "extended_audit (titre)",
    )

    t = unique(
        t,
        'chunks = [c for c in metadata if c.get("departement") == dept]',
        'chunks = [c for c in metadata if dept in departements_du_chunk(c)]',
        "diagnostic_departement",
    )

    t = unique(
        t,
        '"departement": chunk.get("departement"),\n            "_source": origine,',
        '"departement": chunk.get("departement"),\n'
        '            "departements": chunk.get("departements"),\n'
        '            "_source": origine,',
        "search (resultat)",
    )

    t = unique(
        t,
        '"allowed_roles": sorted(effective_allowed_roles(chunk)),',
        '"allowed_roles": sorted(effective_allowed_roles(chunk)),\n'
        '            # Champs lus par effective_allowed_roles(r) dans\n'
        '            # check_rbac_restriction : sans eux, le calcul retombait sur\n'
        '            # RBAC_POLICY seule (faux HORS_PERIMETRE possible). Aucun droit\n'
        '            # n\'est modifie ; "departements" n\'est volontairement PAS\n'
        '            # transporte (il ne participe pas au RBAC).\n'
        '            "access_roles": chunk.get("access_roles"),\n'
        '            "departement": chunk.get("departement"),',
        "search_without_rbac",
    )

    return t


def patcher_ingest(t):
    if 'chunk.get("departements")' in t:
        raise PatchError("ingest_departements.py deja patche (rien a faire).")

    t = regex_unique(
        t,
        r'if chunk\.get\("departement"\):\s+continue',
        'if chunk.get("departement") or chunk.get("departements"):\n'
        '            # deja tagge (mono-departement ou classe multi-departements,\n'
        '            # voir classify_enterprise_departments.py) : jamais ecrase\n'
        '            continue',
        "retag_existing",
    )

    t = unique(
        t,
        'chunks = [c for c in metadata if c.get("departement") == dept]',
        'chunks = [\n'
        '            c for c in metadata\n'
        '            if c.get("departement") == dept\n'
        '            or dept in (c.get("departements") or [])\n'
        '        ]',
        "afficher_audit_departements",
    )

    return t


def traiter(chemin, patcheur, dry_run):
    if not chemin.exists():
        print(f"[ERREUR] {chemin} introuvable.")
        return False

    original = chemin.read_text(encoding="utf-8")

    try:
        nouveau = patcheur(original.replace("\r\n", "\n"))
    except PatchError as e:
        print(f"[{chemin.name}] {e}")
        return "deja" in str(e)

    try:
        ast.parse(nouveau)
    except SyntaxError as e:
        print(f"[ERREUR] {chemin.name} : le resultat ne compile pas ({e}). Rien n'est ecrit.")
        return False

    if dry_run:
        print(f"[dry-run] {chemin.name} : ancrages OK, resultat compilable.")
        return True

    sauvegarde = chemin.with_name(chemin.name + ".bak_multi_dept")
    if not sauvegarde.exists():
        sauvegarde.write_text(original, encoding="utf-8")
    chemin.write_text(nouveau, encoding="utf-8")
    print(f"[OK] {chemin.name} corrige (original : {sauvegarde.name}).")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--assistant", type=Path, default=Path("assistant.py"))
    p.add_argument("--ingest", type=Path, default=Path("ingest_departements.py"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    ok_a = traiter(args.assistant, patcher_assistant, args.dry_run)
    ok_i = traiter(args.ingest, patcher_ingest, args.dry_run)

    print("\nRBAC inchange : effective_allowed_roles() ne lit pas 'departements'.")
    sys.exit(0 if (ok_a and ok_i) else 1)


if __name__ == "__main__":
    main()