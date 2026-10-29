#!/usr/bin/env python3
"""
Ingestion des corpus DEPARTEMENTAUX (Direction, Finance, IT, RH, Commerce,
Juridique, Marketing) dans l'index existant (FAISS + metadata.json).

Objectif (suite de la correction 39/40 d'assistant.py) : faire passer
l'audit

    Audit RBAC EFFECTIF par DEPARTEMENT :
    direction  : 0 chunk indexe
    finance    : 0 chunk indexe
    it         : 0 chunk indexe
    rh         : 0 chunk indexe
    commerce   : 0 chunk indexe
    juridique  : 0 chunk indexe
    marketing  : 0 chunk indexe

de "0 partout" a des comptes REELS, SANS toucher au systeme RBAC par
ENTREPRISE deja en place (Wafa_Assurance, CDG_Capital, Unimer,
Auto_Nejma). Les deux dimensions coexistent sur un meme chunk :

    {
        "entreprise": "Wafa_Assurance",   # dimension existante (peut etre None)
        "departement": "finance",          # nouvelle dimension
        "access_roles": ["finance", "direction", "tous"],
        "type_document": "entreprise",     # ou "public_reglementaire", voir plus bas
        "is_synthetic": false,
        ...
    }

------------------------------------------------------------------------
CE SCRIPT NE CONTIENT AUCUNE DONNEE FABRIQUEE
------------------------------------------------------------------------

Il n'existe plus de corpus de demonstration synthetique dans ce fichier
(l'ancien CORPUS_DEMO / construire_chunks_demo() / --seed-demo ont ete
retires). Un departement sans document reel place sous data/<dept>/ (ou
sans texte reglementaire connu de REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER)
reste a 0 chunk apres execution de ce script -- c'est le comportement
attendu et correct pour une demonstration professionnelle, plutot que
d'afficher des chunks fictifs.

------------------------------------------------------------------------
DEUX NATURES DE DOCUMENTS, DEUX type_document DIFFERENTS
------------------------------------------------------------------------

Un fichier place sous data/<dept>/ peut etre de deux natures tres
differentes, et ce script les distingue explicitement plutot que de tout
etiqueter "entreprise" par defaut :

  1. Un texte REGLEMENTAIRE reel (une loi, un decret, un code) --
     exemples : Code_du_Travail_Loi_65-99.pdf, DNSSI_Directive_Securite_
     SI.pdf, Code_du_Commerce_Loi_15-95.pdf. Ce n'est PAS un document
     interne de l'entreprise : c'est une source publique qui s'applique
     de la meme facon a tout le monde. Un tel fichier est reconnu de
     facon DETERMINISTE par son NOM (voir REGLEMENTAIRE_DEPARTEMENT_PAR_
     FICHIER plus bas -- jamais par une analyse du contenu, qui serait
     approximative), et ingere avec :
         "type_document": "public_reglementaire"
         "entreprise": None
     Le champ "departement" et "access_roles" restent renseignes (utiles
     pour l'audit / le diagnostic "dept <nom>"), mais rappelez-vous que
     est_accessible() et chunk_matches_department() dans assistant.py
     rendent de toute facon TOUJOURS ces documents visibles a tous les
     roles et sous tous les onglets -- c'est voulu : la loi s'applique
     independamment du departement consulte.

  2. Un document interne D'ENTREPRISE (une procedure RH propre a votre
     organisation, vos conditions commerciales, un contrat-cadre que
     vous avez redige...). Celui-la reste ingere avec :
         "type_document": "entreprise"
     et son acces est reellement restreint par role/departement (voir
     DEPARTMENT_ACCESS_ROLES dans assistant.py).

------------------------------------------------------------------------
MODES D'UTILISATION
------------------------------------------------------------------------

1) Ingestion de vrais PDF (mode normal) :

    Placez vos documents dans :
        data/direction/*.pdf
        data/finance/*.pdf
        data/it/*.pdf
        data/rh/*.pdf
        data/commerce/*.pdf
        data/juridique/*.pdf
        data/marketing/*.pdf

    Exemple concret (reprenant les fichiers deja presents dans votre
    dataset) :
        data/it/DNSSI_Directive_Securite_SI.pdf
        data/rh/Code_du_Travail_Loi_65-99.pdf
        data/commerce/Code_du_Commerce_Loi_15-95.pdf
        data/juridique/Code_Obligations_Contrats_DOC.pdf
        data/commerce/Loi_31_08_Protection_Consommateur.pdf

    Puis :
        python ingest_departements.py

    Ou un seul departement :
        python ingest_departements.py --dept it

    Chaque fichier est automatiquement type "public_reglementaire" ou
    "entreprise" selon qu'il correspond ou non a un motif connu de
    REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER -- vous n'avez rien a
    preciser en ligne de commande pour cela.

2) Retagger des chunks DEJA INDEXES qui n'ont pas encore de
   "departement" (typiquement les rapports d'entreprise ingeres par
   votre pipeline d'origine : Wafa_Assurance, CDG_Capital, Unimer,
   Auto_Nejma) :

        python ingest_departements.py --retag-existing

   100% DETERMINISTE : base uniquement sur le nom du fichier
   (fichier_source), via REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER
   (personnalisable avec --retag-map <fichier.json>). Ne recalcule
   AUCUN vecteur FAISS (le texte du chunk ne change pas) : seule la
   metadonnee "departement" (et, si absent, "access_roles") est
   completee. Le type_document et l'entreprise d'origine sont
   PRESERVES : un rapport d'entreprise reste "entreprise", un texte
   de loi reste "public_reglementaire". Si un chunk reglementaire
   connu de REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER porte encore
   type_document == "entreprise" (cas du DNSSI ingere par un pipeline
   plus ancien), sa correction doit se faire avec --retag-map +
   un champ supplementaire, voir plus bas.

3) Simulation sans ecriture :

        python ingest_departements.py --dry-run

   Affiche tout ce qui SERAIT fait (nombre de chunks par departement,
   fichiers lus, retags) sans modifier index.faiss ni metadata.json.

Une sauvegarde horodatee de metadata.json et index.faiss est toujours
ecrite dans data/index/backups/ avant toute modification reelle (donc
jamais en --dry-run), pour pouvoir revenir en arriere si besoin.

Ce script est VOLONTAIREMENT SEPARE de assistant.py (il ne l'importe
pas) : assistant.py initialise un client Groq des son import (arret du
programme si GROQ_API_KEY est absente), ce qui n'a aucun sens pour un
simple script d'ingestion. Les quelques constantes partagees (MODEL_NAME,
DEPARTEMENTS, DEPARTMENT_ACCESS_ROLES, INDEX_DIR) sont dupliquees ici
a l'identique -- si vous les changez dans assistant.py, changez-les ici
aussi (ou factorisez-les dans un module commun `config.py`, voir la note
en bas de fichier).
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        print(
            "Erreur : aucune bibliotheque de lecture PDF trouvee.\n"
            "Installez-en une :\n"
            "    pip install pypdf",
            file=sys.stderr,
        )
        sys.exit(1)


# ============================================================================
# Configuration (dupliquee depuis assistant.py, voir note en bas de fichier)
# ============================================================================

INDEX_DIR = Path("data/index")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

DEPARTEMENTS = [
    "direction",
    "finance",
    "it",
    "rh",
    "commerce",
    "juridique",
    "marketing",
]

DEPARTMENT_ACCESS_ROLES = {
    "direction": ["direction", "tous"],
    "finance": ["finance", "direction", "tous"],
    "it": ["it", "direction", "tous"],
    "rh": ["rh", "direction", "tous"],
    "commerce": ["commerce", "direction", "tous"],
    "juridique": ["juridique", "direction", "tous"],
    "marketing": ["marketing", "direction", "tous"],
}

CHUNK_MAX_CHARS = 1400
CHUNK_MIN_CHARS = 40
CHUNK_OVERLAP = 150


# ============================================================================
# Table de rattachement REGLEMENTAIRE (nom de fichier -> departement)
# ============================================================================
#
# Source UNIQUE de verite pour reconnaitre un texte reglementaire REEL et
# lui attribuer son departement -- de facon deterministe, par nom de
# fichier, jamais par une analyse du contenu (une loi peut mentionner de
# nombreux termes qui la feraient rattacher au mauvais departement par un
# simple comptage de mots-cles ; le nom du texte de loi, lui, ne ment
# pas). Utilisee a la fois par :
#   - construire_chunks_pdf() : pour typer correctement un NOUVEAU PDF
#     ingere depuis data/<dept>/ (public_reglementaire vs entreprise) ;
#   - retag_existing() : pour completer les chunks DEJA indexes par
#     votre pipeline d'origine qui n'ont pas encore de departement.
#
# Completez cette table au fur et a mesure que vous identifiez de
# nouveaux textes reglementaires dans votre corpus -- ou surchargez-la
# entierement via --retag-map <fichier.json> (meme format : {motif
# regex: departement}) sans modifier ce fichier.
REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER = {
    r"DNSSI": "it",
    r"[Ss]ecurite[_ ]SI": "it",
    r"S[ée]curit[ée][_ ]Informatique": "it",
    r"Code_du_Travail": "rh",
    r"Loi_65[-_]99": "rh",
    r"Code_du_Commerce": "commerce",
    r"Loi_15[-_]95": "commerce",
    r"Code_Obligations_Contrats": "juridique",
    r"Code_des?_Obligations": "juridique",
    r"\bDOC\b": "juridique",
    r"Loi_31[-_]08": "commerce",
    r"Protection_Consommateur": "commerce",
    r"Loi_09[-_]08": "juridique",
    r"Donnees_Personnelles": "juridique",
    r"Code_de_Commerce": "commerce",
}


def classifier_document_reglementaire(nom_fichier: str) -> str | None:
    """
    Retourne le departement associe a un nom de fichier reglementaire
    connu (REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER), ou None si ce nom de
    fichier ne correspond a aucun texte reglementaire reconnu -- auquel
    cas le fichier est traite comme un document d'entreprise ordinaire
    (voir construire_chunks_pdf()).

    100% deterministe : un seul re.search() par motif connu, pas
    d'analyse du contenu du document.
    """
    for motif, dept in REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER.items():
        if re.search(motif, nom_fichier, flags=re.IGNORECASE):
            return dept
    return None


# ============================================================================
# Chargement / sauvegarde de l'index
# ============================================================================

def load_index_and_metadata():
    index_path = INDEX_DIR / "index.faiss"
    metadata_path = INDEX_DIR / "metadata.json"

    if not index_path.exists() or not metadata_path.exists():
        print(
            f"Erreur : {index_path} ou {metadata_path} introuvable. "
            "Lancez d'abord votre pipeline d'ingestion initial.",
            file=sys.stderr,
        )
        sys.exit(1)

    index = faiss.read_index(str(index_path))

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    if index.ntotal != len(metadata):
        print(
            f"/!\\ ATTENTION : index.ntotal={index.ntotal} != "
            f"len(metadata)={len(metadata)}. L'index FAISS et "
            f"metadata.json sont desynchronises -- ARRET par securite "
            f"pour ne pas aggraver la desynchronisation.",
            file=sys.stderr,
        )
        sys.exit(1)

    return index, metadata


def save_index_and_metadata(index, metadata):
    """Sauvegarde avec backup horodate prealable (jamais appelee en dry-run)."""

    backup_dir = INDEX_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    index_path = INDEX_DIR / "index.faiss"
    metadata_path = INDEX_DIR / "metadata.json"

    if index_path.exists():
        faiss.write_index(
            faiss.read_index(str(index_path)), str(backup_dir / f"index_{ts}.faiss")
        )
    if metadata_path.exists():
        (backup_dir / f"metadata_{ts}.json").write_bytes(metadata_path.read_bytes())

    faiss.write_index(index, str(index_path))

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"\nSauvegarde : {backup_dir}/index_{ts}.faiss + metadata_{ts}.json")
    print(f"Index mis a jour : {index_path} ({index.ntotal} vecteurs)")
    print(f"Metadonnees mises a jour : {metadata_path} ({len(metadata)} chunks)")


# ============================================================================
# Extraction et chunking de PDF
# ============================================================================

def extraire_pages(pdf_path: Path):
    """Genere (numero_page, texte_normalise) pour chaque page non vide."""

    reader = PdfReader(str(pdf_path))

    for i, page in enumerate(reader.pages, start=1):

        try:
            texte = page.extract_text() or ""
        except Exception as e:
            print(f"   /!\\ Erreur extraction page {i} de {pdf_path.name} : {e}")
            continue

        texte = re.sub(r"\s+", " ", texte).strip()

        if texte:
            yield i, texte


def chunker_texte(texte: str, max_chars=CHUNK_MAX_CHARS, overlap=CHUNK_OVERLAP):
    """Decoupe un texte de page en chunks de taille raisonnable, en essayant
    de couper sur une frontiere de phrase plutot qu'au milieu d'un mot."""

    if len(texte) <= max_chars:
        yield texte
        return

    debut = 0

    while debut < len(texte):

        fin = min(len(texte), debut + max_chars)

        coupe = texte.rfind(". ", debut, fin)

        if coupe == -1 or coupe < debut + int(max_chars * 0.5):
            coupe = fin
        else:
            coupe += 1

        morceau = texte[debut:coupe].strip()

        if morceau:
            yield morceau

        if coupe >= len(texte):
            break

        debut = max(coupe - overlap, debut + 1)


def deviner_entreprise(pdf_path: Path, noms_connus: set) -> str | None:
    """
    Devine l'entreprise concernee a partir du nom de fichier, si un nom
    connu (Wafa_Assurance, CDG_Capital, Unimer, Auto_Nejma...) y figure.

    N'est appelee QUE pour les documents d'ENTREPRISE (voir
    construire_chunks_pdf()) -- un texte reglementaire reel n'appartient
    a aucune entreprise particuliere, entreprise reste None pour ces
    fichiers-la, meme si leur nom contenait par accident un nom connu.
    """

    nom_fichier = pdf_path.stem.lower().replace("-", "_")

    for nom in noms_connus:

        variante_espace = nom.lower().replace("_", " ")

        if nom.lower() in nom_fichier or variante_espace in nom_fichier.replace("_", " "):
            return nom

    return None


def construire_chunks_pdf(pdf_path: Path, departement_dossier: str, noms_connus: set):
    """
    Construit la liste de chunks (schema metadata.json) pour un PDF,
    en determinant D'ABORD s'il s'agit d'un texte reglementaire REEL
    reconnu (REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER) ou d'un document
    d'entreprise ordinaire -- les deux cas produisent un type_document
    different (voir docstring du module).

    Retourne (chunks, avertissement) ou avertissement est une chaine non
    vide si le departement devine par le nom de fichier reglementaire
    differe du dossier data/<departement_dossier>/ dans lequel le
    fichier a ete place (incoherence a signaler, pas bloquante -- le nom
    de fichier reste la source de verite pour le departement d'un texte
    reglementaire, voir REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER).
    """

    dept_reglementaire = classifier_document_reglementaire(pdf_path.name)

    avertissement = ""

    if dept_reglementaire is not None:
        departement = dept_reglementaire
        type_document = "public_reglementaire"
        entreprise = None

        if dept_reglementaire != departement_dossier:
            avertissement = (
                f"le nom de fichier indique le departement "
                f"'{dept_reglementaire}' mais le fichier est place dans "
                f"data/{departement_dossier}/ -- le departement "
                f"'{dept_reglementaire}' (issu du nom de fichier) est "
                f"utilise pour le tag, deplacez le fichier dans "
                f"data/{dept_reglementaire}/ pour lever cette incoherence."
            )
    else:
        departement = departement_dossier
        type_document = "entreprise"
        entreprise = deviner_entreprise(pdf_path, noms_connus)

    chunks = []

    for page_num, texte_page in extraire_pages(pdf_path):

        for morceau in chunker_texte(texte_page):

            if len(morceau) < CHUNK_MIN_CHARS:
                continue

            chunks.append({
                "content": morceau,
                "fichier_source": pdf_path.name,
                "page": page_num,
                "entreprise": entreprise,
                "secteur": None,
                "departement": departement,
                "access_roles": list(DEPARTMENT_ACCESS_ROLES[departement]),
                "type_document": type_document,
                "is_synthetic": False,
            })

    return chunks, avertissement


def ingerer_departement_pdfs(dept: str, noms_connus: set):
    """Lit tous les PDF de data/<dept>/ et retourne la liste des chunks."""

    dossier = Path("data") / dept

    if not dossier.exists():
        print(f"   {dept:10s} : dossier data/{dept}/ absent, ignore.")
        return []

    pdfs = sorted(dossier.glob("*.pdf"))

    if not pdfs:
        print(f"   {dept:10s} : dossier data/{dept}/ vide (aucun *.pdf).")
        return []

    tous_chunks = []

    for pdf_path in pdfs:

        chunks, avertissement = construire_chunks_pdf(pdf_path, dept, noms_connus)

        if not chunks:
            print(f"   {dept:10s} : {pdf_path.name} -> 0 chunk (PDF vide ou illisible)")
            continue

        nature = chunks[0]["type_document"]
        suffixe_entreprise = (
            f" [entreprise={chunks[0]['entreprise']}]" if chunks[0]["entreprise"] else ""
        )

        print(
            f"   {dept:10s} : {pdf_path.name} -> {len(chunks)} chunk(s) "
            f"[{nature}]{suffixe_entreprise}"
        )

        if avertissement:
            print(f"      /!\\ {avertissement}")

        tous_chunks.extend(chunks)

    return tous_chunks


# ============================================================================
# Retag de chunks DEJA INDEXES (rapports d'entreprise et/ou textes
# reglementaires) n'ayant pas encore de "departement".
# ============================================================================
#
# CORRECTION (voir note en bas de fichier) : cette fonction ne touche PLUS
# a "type_document" ni a "entreprise". Elle se contente d'ajouter le tag
# "departement" (et "access_roles" si absent) aux chunks orphelins.
#
# Raison : les rapports d'entreprise (Wafa_Assurance_RFA, CDG_Capital_RFA,
# UNIMER_RFA, Auto_Nejma_RFA) sont de VRAIS documents d'entreprise, pas
# des textes de loi. La version precedente les convertissait a tort en
# "public_reglementaire" avec entreprise=None -- ce qui les aurait rendus
# accessibles a TOUS les roles via effective_allowed_roles(), cassant
# tout le RBAC.

def retag_existing(metadata: list, mapping: dict) -> int:
    """
    Complete la metadonnee "departement" (et "access_roles" si absent)
    des chunks DEJA INDEXES qui n'en ont pas encore, par correspondance
    DETERMINISTE de nom de fichier (fichier_source) contre `mapping`
    (REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER par defaut, ou --retag-map
    personnalise).

    Ne touche JAMAIS un chunk qui porte deja un "departement" (pas
    d'ecrasement silencieux d'un tag existant). Ne recalcule AUCUN
    vecteur FAISS : le contenu textuel est inchange.

    PRESERVE type_document et entreprise : un rapport d'entreprise reste
    "entreprise" avec son entreprise d'origine ; un texte de loi garde
    "public_reglementaire" avec entreprise=None.

    Retourne le nombre de chunks retagges.
    """

    n_departement_ajoute = 0

    for chunk in metadata:

        if chunk.get("departement") or chunk.get("departements"):
            # deja tagge (mono-departement ou classe multi-departements,
            # voir classify_enterprise_departments.py) : jamais ecrase
            continue

        fichier = chunk.get("fichier_source", "") or ""

        for motif, dept in mapping.items():

            if dept not in DEPARTEMENTS:
                continue

            if not re.search(motif, fichier, flags=re.IGNORECASE):
                continue

            chunk["departement"] = dept

            if not chunk.get("access_roles"):
                chunk["access_roles"] = list(DEPARTMENT_ACCESS_ROLES[dept])

            # NOTE : on ne touche NI a chunk["type_document"] NI a
            # chunk["entreprise"] ici. Un rapport d'entreprise reste
            # "entreprise" ; un texte de loi reste "public_reglementaire".
            # Voir la docstring ci-dessus pour la raison.

            n_departement_ajoute += 1
            break

    return n_departement_ajoute


# ============================================================================
# Audit rapide post-ingestion (meme logique que extended_audit_allowed_roles
# dans assistant.py, dupliquee ici pour ne pas dependre de ce module)
# ============================================================================

def afficher_audit_departements(metadata: list):

    print("\nEtat des departements apres cette execution :")

    for dept in DEPARTEMENTS:

        chunks = [
            c for c in metadata
            if c.get("departement") == dept
            or dept in (c.get("departements") or [])
        ]

        if not chunks:
            print(f"   {dept:10s} : 0 chunk indexe")
            continue

        n_entreprise = sum(
            1 for c in chunks if c.get("type_document", "entreprise") == "entreprise"
        )
        n_reglementaire = sum(
            1 for c in chunks
            if c.get("type_document", "entreprise") == "public_reglementaire"
        )
        n_synthetic = sum(1 for c in chunks if c.get("is_synthetic"))

        detail = (
            f"{len(chunks)} chunks (entreprise={n_entreprise}, "
            f"reglementaire={n_reglementaire}"
        )

        if n_synthetic:
            detail += f", /!\\ demo_synthetique={n_synthetic}"

        detail += ")"

        print(f"   {dept:10s} : {detail}")

    print()


# ============================================================================
# Point d'entree
# ============================================================================

def main():

    parser = argparse.ArgumentParser(
        description="Ingestion des corpus departementaux REELS dans l'index existant."
    )
    parser.add_argument(
        "--dept",
        choices=DEPARTEMENTS,
        default=None,
        help="Limiter l'ingestion des PDF a un seul departement.",
    )
    parser.add_argument(
        "--retag-existing",
        action="store_true",
        help="Ajouter la metadonnee 'departement' (et 'access_roles' si "
             "absent) aux chunks deja indexes qui n'en ont pas, par "
             "correspondance DETERMINISTE de nom de fichier. Ne touche "
             "NI 'type_document' NI 'entreprise'.",
    )
    parser.add_argument(
        "--retag-map",
        type=Path,
        default=None,
        help="Fichier JSON {motif_regex: departement} pour personnaliser "
             "--retag-existing (remplace REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="N'ecrit rien sur disque, affiche seulement ce qui serait fait.",
    )

    args = parser.parse_args()

    print("Chargement de l'index existant...")
    index, metadata = load_index_and_metadata()
    print(f"{index.ntotal} chunks actuellement indexes.\n")

    noms_connus = {c.get("entreprise") for c in metadata if c.get("entreprise")}

    total_nouveaux_chunks = []
    n_retagges = 0

    # --- Retag des chunks deja indexes sans departement --------------------
    if args.retag_existing:

        mapping = REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER

        if args.retag_map:
            with open(args.retag_map, "r", encoding="utf-8") as f:
                mapping = json.load(f)

        print("Retag des chunks existants sans departement :")
        for motif, dept in mapping.items():
            print(f"   motif '{motif}' -> departement '{dept}'")

        n_retagges = retag_existing(metadata, mapping)

        print(f"-> {n_retagges} chunk(s) retagge(s).")
        print()

    # --- Ingestion des PDF reels -----------------------------------------
    departements_a_traiter = [args.dept] if args.dept else DEPARTEMENTS

    print("Ingestion des PDF departementaux (data/<dept>/*.pdf) :")
    for dept in departements_a_traiter:
        total_nouveaux_chunks.extend(
            ingerer_departement_pdfs(dept, noms_connus)
        )

    if not total_nouveaux_chunks and not n_retagges:
        print(
            "\nAucun nouveau chunk a ajouter et aucune metadonnee modifiee. "
            "Rien a faire."
        )
        return

    # --- Embeddings + ecriture ---------------------------------------------
    if total_nouveaux_chunks:

        n_entreprise = sum(
            1 for c in total_nouveaux_chunks if c["type_document"] == "entreprise"
        )
        n_reglementaire = sum(
            1 for c in total_nouveaux_chunks
            if c["type_document"] == "public_reglementaire"
        )

        print(
            f"\n{len(total_nouveaux_chunks)} nouveau(x) chunk(s) au total "
            f"a embedder et indexer (entreprise={n_entreprise}, "
            f"reglementaire={n_reglementaire})."
        )

        if args.dry_run:
            print("[dry-run] Embeddings et ecriture ignores.")
        else:
            print("Chargement du modele d'embeddings...")
            model = SentenceTransformer(MODEL_NAME)

            textes = [c["content"] for c in total_nouveaux_chunks]

            print("Calcul des embeddings...")
            vecteurs = model.encode(
                textes, convert_to_numpy=True, show_progress_bar=True
            ).astype("float32")

            faiss.normalize_L2(vecteurs)

            index.add(vecteurs)
            metadata.extend(total_nouveaux_chunks)

    if args.dry_run:
        print("\n[dry-run] Aucune ecriture sur disque (index.faiss / metadata.json inchanges).")
    else:
        save_index_and_metadata(index, metadata)

    afficher_audit_departements(metadata)


if __name__ == "__main__":
    main()


# ============================================================================
# Note de factorisation (optionnelle, non appliquee ici)
# ============================================================================
#
# INDEX_DIR, MODEL_NAME, DEPARTEMENTS et DEPARTMENT_ACCESS_ROLES sont
# dupliques entre assistant.py et ce script. Ce n'est pas une erreur --
# c'est un choix deliberer pour que ce script d'ingestion reste
# executable independamment (sans client Groq, sans GROQ_API_KEY) -- mais
# si vous preferez une seule source de verite, il est facile d'extraire
# ces quatre constantes (et REGLEMENTAIRE_DEPARTEMENT_PAR_FICHIER) dans
# un fichier config.py que les deux scripts importeraient, sans rien
# changer d'autre a leur fonctionnement respectif.