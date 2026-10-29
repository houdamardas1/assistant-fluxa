#!/usr/bin/env python3
"""
Genere des documents synthetiques (FICTIFS, clairement etiquetes comme demo)
pour les departements IT, RH, Commerce, Juridique, Marketing - qui n'ont pas
d'equivalent en donnees publiques marocaines, contrairement a la Finance (AMMC).

Ces documents servent uniquement a demontrer que l'architecture RBAC/RAG
est generalisable a plusieurs departements. Ils ne represent AUCUNE
entreprise reelle - "Entreprise Demo SA" est un nom fictif.

A executer depuis backend/, avant ingest_reports.py sur ces nouveaux docs.

Usage:
    python generate_synthetic_docs.py
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from langchain.text_splitter import RecursiveCharacterTextSplitter

BASE_PATH = Path("data/raw")
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
    length_function=len,
)

# ============================================================
# CONTENU SYNTHETIQUE - clairement fictif, "Entreprise Demo SA"
# ============================================================

DEPARTEMENTS = {
    "it": {
        "entreprise": "Entreprise_Demo_SA",
        "fichier_source": "Politique_IT_Demo.txt (SYNTHETIQUE)",
        "allowed_roles": ["tous", "it", "direction"],
        "pages": [
            """POLITIQUE DE SECURITE INFORMATIQUE - ENTREPRISE DEMO SA (DOCUMENT FICTIF - DEMONSTRATION)

Article 1 - Gestion des acces
Tout collaborateur dispose d'un compte utilisateur unique associe a son identite professionnelle. Les acces aux systemes sont attribues selon le principe du moindre privilege : chaque utilisateur n'a acces qu'aux ressources strictement necessaires a sa fonction. Toute demande d'acces supplementaire doit etre validee par le responsable hierarchique et le service IT.

Article 2 - Mots de passe et authentification
Les mots de passe doivent contenir au minimum 12 caracteres, incluant majuscules, minuscules, chiffres et caracteres speciaux. L'authentification multi-facteurs (MFA) est obligatoire pour l'acces aux systemes critiques (messagerie, VPN, applications metier sensibles). Le renouvellement des mots de passe est requis tous les 90 jours.

Article 3 - Gestion des incidents
Tout incident de securite (perte d'equipement, suspicion de phishing, acces non autorise) doit etre signale immediatement au Service Desk IT via le numero d'urgence interne ou le portail de tickets. Le delai de traitement cible pour un incident critique est de 4 heures ouvrees.""",
            """PROCEDURE DE DEMANDE D'EQUIPEMENT INFORMATIQUE (DOCUMENT FICTIF - DEMONSTRATION)

Toute demande d'equipement (ordinateur, telephone professionnel, acces logiciel) doit etre soumise via le portail interne de tickets IT. Le delai de traitement standard est de 5 jours ouvres pour un equipement standard, et de 10 jours ouvres pour un equipement necessitant une validation budgetaire specifique.

Criteres de priorisation des tickets :
- Priorite 1 (urgent) : panne bloquante empechant le travail
- Priorite 2 (haute) : ralentissement significatif de l'activite
- Priorite 3 (normale) : demande d'evolution ou de nouvel equipement

Le taux de resolution au premier contact vise par le Service Desk est de 65%. Un rapport mensuel des incidents et de leur resolution est transmis a la Direction IT.""",
        ],
    },
    "rh": {
        "entreprise": "Entreprise_Demo_SA",
        "fichier_source": "Politique_RH_Demo.txt (SYNTHETIQUE)",
        "allowed_roles": ["tous", "rh", "direction"],
        "pages": [
            """POLITIQUE DE CONGES ET ABSENCES - ENTREPRISE DEMO SA (DOCUMENT FICTIF - DEMONSTRATION)

Article 1 - Conges payes
Chaque collaborateur beneficie de 22 jours de conges payes par annee complete de travail, conformement a la legislation en vigueur. Les demandes de conges doivent etre soumises au moins 15 jours a l'avance via le portail RH, et validees par le responsable hierarchique direct.

Article 2 - Conges exceptionnels
Des conges exceptionnels sont accordes pour evenements familiaux : mariage du collaborateur (4 jours), naissance ou adoption (3 jours), deces d'un proche (2 a 5 jours selon le lien de parente). Ces conges ne sont pas deductibles des conges payes annuels.

Article 3 - Teletravail
Le teletravail est accessible aux postes eligibles apres 6 mois d'anciennete, dans la limite de 2 jours par semaine, sous validation du responsable hierarchique. Une charte de teletravail specifique detaille les conditions materielles et de disponibilite attendues.""",
            """PROCEDURE DE RECRUTEMENT INTERNE (DOCUMENT FICTIF - DEMONSTRATION)

Le processus de recrutement se deroule en 4 etapes : publication du poste sur le portail interne, preselection des candidatures par le service RH, entretiens avec le manager et le RH, puis decision finale validee par la Direction pour les postes de niveau cadre.

Delai moyen du processus de recrutement : 6 semaines entre la publication et la decision finale. Le taux de mobilite interne cible par la Direction RH est de 15% des postes ouverts par an.

Les collaborateurs disposant d'au moins 12 mois d'anciennete sont prioritaires pour les candidatures internes, sous reserve de l'accord de leur responsable hierarchique actuel.""",
        ],
    },
    "commerce": {
        "entreprise": "Entreprise_Demo_SA",
        "fichier_source": "Procedure_Commerciale_Demo.txt (SYNTHETIQUE)",
        "allowed_roles": ["tous", "commerce", "direction"],
        "pages": [
            """PROCEDURE DE GESTION DES OFFRES COMMERCIALES (DOCUMENT FICTIF - DEMONSTRATION)

Article 1 - Elaboration des offres
Toute offre commerciale superieure a 500 000 MAD doit faire l'objet d'une validation par le responsable commercial regional avant envoi au client. Les offres superieures a 2 000 000 MAD necessitent en plus une validation de la Direction Commerciale.

Article 2 - Delais de reponse client
Le delai cible de reponse a une demande de devis est de 48 heures ouvrees pour les clients existants, et de 5 jours ouvres pour les nouveaux prospects necessitant une qualification prealable.

Article 3 - Suivi du pipeline commercial
Chaque commercial met a jour son pipeline d'opportunites dans le CRM au minimum une fois par semaine. Le taux de conversion moyen vise sur les opportunites qualifiees est de 25%.""",
        ],
    },
    "juridique": {
        "entreprise": "Entreprise_Demo_SA",
        "fichier_source": "Procedure_Juridique_Demo.txt (SYNTHETIQUE)",
        "allowed_roles": ["tous", "juridique", "direction"],
        "pages": [
            """PROCEDURE DE VALIDATION DES CONTRATS (DOCUMENT FICTIF - DEMONSTRATION)

Article 1 - Circuit de validation
Tout contrat client ou fournisseur doit etre soumis au service juridique pour revue avant signature. Le delai standard de revue est de 5 jours ouvres pour un contrat type, et de 10 jours ouvres pour un contrat comportant des clauses non standard.

Article 2 - Seuils de delegation de signature
Les contrats d'un montant inferieur a 300 000 MAD peuvent etre signes par le responsable de departement concerne. Au-dela de ce seuil, la signature de la Direction Generale est requise, apres avis du service juridique.

Article 3 - Suivi des echeances contractuelles
Le service juridique maintient un registre des contrats en cours avec alerte automatique 60 jours avant echeance ou tacite reconduction, transmise au responsable de departement concerne.""",
        ],
    },
    "marketing": {
        "entreprise": "Entreprise_Demo_SA",
        "fichier_source": "Guide_Marketing_Demo.txt (SYNTHETIQUE)",
        "allowed_roles": ["tous", "marketing", "direction"],
        "pages": [
            """CHARTE DE COMMUNICATION ET MARQUE (DOCUMENT FICTIF - DEMONSTRATION)

Article 1 - Identite visuelle
Toute communication externe (supports imprimes, digitaux, reseaux sociaux) doit respecter la charte graphique validee par la Direction Marketing, incluant les couleurs, typographies et logo officiels de l'entreprise.

Article 2 - Validation des campagnes
Les campagnes marketing d'un budget superieur a 100 000 MAD sont soumises a validation du comite marketing avant lancement. Le delai moyen de validation est de 10 jours ouvres.

Article 3 - Mesure de performance
Chaque campagne fait l'objet d'un bilan de performance a J+30, incluant le taux d'engagement, le cout par acquisition, et le retour sur investissement estime. L'objectif annuel de notoriete assistee de la marque est fixe par la Direction Generale.""",
        ],
    },
}


def process_department(dept_key: str, dept_data: dict):
    print(f"Generation : {dept_key} ({dept_data['entreprise']})")

    chunks = []
    for page_num, page_text in enumerate(dept_data["pages"], start=1):
        for chunk_text in splitter.split_text(page_text):
            if len(chunk_text.strip()) < 50:
                continue
            chunks.append({"page": page_num, "content": chunk_text})

    result = {
        "entreprise": dept_data["entreprise"],
        "secteur": dept_key,
        "fichier_source": dept_data["fichier_source"],
        "nb_pages_total": len(dept_data["pages"]),
        "nb_pages_low_text": 0,
        "pages_low_text": [],
        "nb_chunks": len(chunks),
        "allowed_roles": dept_data["allowed_roles"],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "is_synthetic": True,  # <-- marqueur explicite : donnee fictive, pas reelle
        "chunks": chunks,
    }

    out_dir = BASE_PATH / dept_key / dept_data["entreprise"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{dept_data['entreprise']}_chunks.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  -> {len(chunks)} chunks -> {out_path}")


def main():
    for dept_key, dept_data in DEPARTEMENTS.items():
        process_department(dept_key, dept_data)

    print("\nTermine. Ces documents sont SYNTHETIQUES (is_synthetic: true dans le JSON).")
    print("Prochaine etape : relance build_index.py pour les inclure dans l'index.")


if __name__ == "__main__":
    main()