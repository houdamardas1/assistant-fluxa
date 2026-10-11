#!/usr/bin/env python3
"""
Genere des documents de reference REELS pour les departements IT, RH,
Commerce, Juridique, Marketing - bases sur de vraies lois et directives
marocaines publiques, pas sur du contenu invente.

Sources reelles utilisees (citees dans chaque document) :
- IT        : Directive Nationale de la Securite des SI (DNSSI), DGSSI
- RH        : Code du Travail marocain, Loi 65-99, articles 231-246
- Commerce  : Code de Commerce marocain, Loi 15-95
- Juridique : Dahir formant Code des Obligations et des Contrats (DOC), 1913
- Marketing : Loi 31-08 sur la protection du consommateur (regles publicitaires)

Le contenu ci-dessous est REFORMULE (paraphrase) a partir des dispositions
reelles de ces textes, pas copie mot pour mot - avec citation de la loi
et de l'article source a chaque fois, pour verification.

A executer depuis backend/, avant build_index.py.

Usage:
    python generate_legal_reference_docs.py
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

DEPARTEMENTS = {
    "it": {
        "entreprise": "Cadre_Reglementaire_Maroc",
        "fichier_source": "DNSSI - Directive Nationale de la Securite des SI (DGSSI)",
        "source_url": "https://www.dgssi.gov.ma/sites/default/files/publications/pdf/2023-02/directive_nationale_de_la_securite_si_vf_12012023-3.pdf",
        "allowed_roles": ["tous", "it", "direction"],
        "pages": [
            """CADRE DE SECURITE DES SYSTEMES D'INFORMATION AU MAROC
Source : Directive Nationale de la Securite des Systemes d'Information (DNSSI), publiee par la Direction Generale de la Securite des Systemes d'Information (DGSSI), version consolidee 2023.

La DGSSI est l'autorite marocaine competente en matiere de cybersecurite, creee par le decret n 2-11-509 du 21 septembre 2011. Elle applique notamment la loi 05-20 relative a la cybersecurite et pilote le maCERT (Moroccan Computer Emergency Response Team), charge de la veille et de la reponse aux incidents de securite affectant les systemes d'information.

La DNSSI impose un ensemble de regles de securite applicables aux systemes d'information. Parmi les obligations principales : l'interdiction stricte d'utiliser tout logiciel sans licence en regle, la protection des donnees a caractere personnel conformement a la reglementation en vigueur, et l'obligation de faire signer une charte d'utilisation des systemes d'information par chaque utilisateur - cette charte, validee par la hierarchie, constitue un element opposable en cas de manquement grave.

La directive recommande egalement le cloisonnement des reseaux informatiques en sous-reseaux pour ameliorer la securite globale, ainsi que l'organisation reguliere d'exercices de crise pour tester les moyens de secours selon differents scenarios.""",
            """AUDIT ET GOUVERNANCE DE LA SECURITE INFORMATIQUE (DNSSI, DGSSI)

Selon la DNSSI, les organismes concernes doivent mener des operations d'audit de leurs systemes d'information au moins une fois tous les deux ans. Chaque audit doit donner lieu a des recommandations concretes, mises en oeuvre dans le cadre de plans d'actions definis en concertation avec les structures concernees.

En cas d'incident de securite touchant une ressource sensible (materiel, logiciel, donnee ou procedure composant un systeme d'information), un compte rendu d'execution doit etre transmis a la DGSSI. Les entites disposant d'infrastructures d'importance vitale (IIV) sont soumises a des obligations renforcees, notamment concernant le recours a des prestataires de services Cloud, encadre depuis 2024 par le decret n 2-24-921.

La DGSSI publie egalement des referentiels techniques specifiques, dont un guide relatif a la securite des systemes d'information industriels et des recommandations sur la configuration securisee des protocoles reseau (BGP, DNS)."""],
    },
    "rh": {
        "entreprise": "Cadre_Reglementaire_Maroc",
        "fichier_source": "Code du Travail marocain - Loi 65-99 (articles 231-246)",
        "source_url": "https://adala.ai/blog/code-du-travail-maroc/",
        "allowed_roles": ["tous", "rh", "direction"],
        "pages": [
            """CONGES PAYES - CADRE LEGAL MAROCAIN
Source : Code du Travail marocain, Loi 65-99 du 11 septembre 2003, entree en vigueur le 8 juin 2004 (589 articles, 7 livres). Dispositions sur les conges : articles 231 a 246.

Tout salarie a droit, apres six mois de service continu chez le meme employeur, a un conge annuel paye. La duree minimale legale est d'un jour et demi de travail effectif par mois de service, soit un minimum de 18 jours ouvrables par an pour la premiere periode. Ce minimum peut etre ameliore par le reglement interieur de l'entreprise, une convention collective, ou un accord individuel - mais jamais reduit en-dessous du seuil legal.

L'article 240 autorise, par accord entre le salarie et l'employeur, le fractionnement ou le cumul du conge annuel sur deux annees consecutives, a condition que la duree du conge ne descende jamais en-dessous de douze jours ouvrables incluant deux jours de repos hebdomadaire.

L'employeur doit communiquer l'ordre des departs en conge au moins 30 jours a l'avance, l'afficher dans l'entreprise et l'inscrire sur un registre accessible aux salaries.""",
            """CONGES EXCEPTIONNELS ET DUREE DU TRAVAIL - CODE DU TRAVAIL MAROCAIN

Au-dela du conge annuel paye, le Code du Travail marocain prevoit des conges exceptionnels pour evenements familiaux, non deductibles du conge annuel : mariage du salarie (4 jours), et deces d'un proche (3 jours selon le lien de parente concerne).

La duree normale du travail est fixee par l'article 184 a 44 heures par semaine dans les activites non agricoles, reparties selon les besoins de l'entreprise. Le salaire minimum interprofessionnel garanti (SMIG) et les regles de remuneration sont egalement encadres par le meme texte legal.

Le Code du Travail interdit par ailleurs toute discrimination et toute atteinte a la dignite du salarie, y compris le harcelement moral ou sexuel (article 24), et fixe l'age minimum d'admission au travail a 15 ans (article 143), les travaux dangereux etant interdits aux salaries de moins de 18 ans (article 147)."""],
    },
    "commerce": {
        "entreprise": "Cadre_Reglementaire_Maroc",
        "fichier_source": "Code de Commerce marocain - Loi 15-95",
        "source_url": "https://oriental.eregulations.org/media/code%20de%20commerce%20marocain.pdf",
        "allowed_roles": ["tous", "commerce", "direction"],
        "pages": [
            """CADRE JURIDIQUE DE L'ACTIVITE COMMERCIALE AU MAROC
Source : Loi n 15-95 formant Code de Commerce, promulguee par le Dahir n 1-96-83 du 1er aout 1996 (Bulletin Officiel n 4418 du 3 octobre 1996), version consolidee.

Le Code de Commerce regit les actes de commerce et le statut de commercant. Toute personne physique ou morale, marocaine ou etrangere, exercant une activite commerciale sur le territoire du Royaume est tenue de s'immatriculer au registre du commerce (article 37). Cette obligation s'applique egalement aux succursales et agences d'entreprises marocaines ou etrangeres, qui doivent etre immatriculees dans les trois mois suivant leur ouverture.

Tout commercant a l'obligation d'ouvrir un compte bancaire pour les besoins de son commerce (article 18), et doit tenir une comptabilite conforme a la loi n 9-88 relative aux obligations comptables des commercants. En matiere commerciale, les litiges sont regles conformement aux lois, coutumes et usages du commerce ; a defaut, le droit civil s'applique dans la mesure ou il ne contredit pas les principes du droit commercial (article 2).""",
            """FONDS DE COMMERCE ET REGISTRE DE COMMERCE - CODE DE COMMERCE MAROCAIN

Le Code de Commerce organise egalement le regime du fonds de commerce : sa composition, sa vente, son nantissement et sa location-gerance (Livre II). Toute inscription au registre du commerce pour laquelle aucun delai specifique n'est fixe doit etre requise dans le mois suivant l'acte ou le fait a inscrire.

La loi encadre aussi les difficultes de l'entreprise (Livre VI), incluant les procedures applicables en cas de defaillance financiere d'une societe commerciale. Le texte a ete complete au fil du temps, notamment par la loi n 21-18 relative aux suretes mobilieres et la loi n 73-17 relative aux difficultes de l'entreprise, integrees dans la version consolidee de decembre 2019."""],
    },
    "juridique": {
        "entreprise": "Cadre_Reglementaire_Maroc",
        "fichier_source": "Dahir formant Code des Obligations et des Contrats (DOC)",
        "source_url": "https://rabat.eregulations.org/media/doc%20maroc.pdf",
        "allowed_roles": ["tous", "juridique", "direction"],
        "pages": [
            """VALIDITE DES CONTRATS - CADRE LEGAL MAROCAIN (DOC)
Source : Dahir du 12 aout 1913 (9 ramadan 1331) formant Code des Obligations et des Contrats (D.O.C.), texte fondateur du droit des contrats au Maroc, toujours en vigueur (version consolidee 2019).

Selon l'article premier du DOC, les obligations derivent des conventions et autres declarations de volonte, des quasi-contrats, des delits et des quasi-delits. L'article 2 precise les elements necessaires a la validite d'une obligation issue d'une declaration de volonte : une capacite valable des parties, une declaration de volonte valable, un objet certain pouvant former matiere d'obligation, et une cause licite.

Depuis la loi n 53-05 de 2007, un contrat peut etre valablement etabli et conserve sous forme electronique, y compris lorsqu'un ecrit est legalement exige pour sa validite, a condition que les modalites garantissent l'integrite et la tracabilite de l'engagement (article 2-1 et articles 65 et suivants relatifs au contrat electronique).

Le mineur et l'incapable ayant contracte sans l'autorisation de leur representant legal ne sont pas engages par leurs obligations et peuvent en demander la rescision, sauf approbation posterieure du representant dans la forme requise par la loi (article 4).""",
            """CESSION DE CREANCES ET OBLIGATIONS CONTRACTUELLES - DOC MAROCAIN

Le DOC encadre egalement la cession de baux, loyers et creances : une cession n'a d'effet a l'egard des tiers que si elle est constatee par un ecrit ayant date certaine, notamment pour les cessions portant sur une periode significative (article 196).

Ce texte, bien qu'ancien (1913), demeure la base du droit des obligations au Maroc et s'articule avec des textes plus recents comme le Code de Commerce (loi 15-95) pour les actes de nature commerciale, ainsi qu'avec le Code de la Famille (loi 70-03) pour les questions de capacite juridique des personnes physiques, notamment la majorite legale fixee a 18 ans revolus (article 209 du Code de la Famille)."""],
    },
    "marketing": {
        "entreprise": "Cadre_Reglementaire_Maroc",
        "fichier_source": "Loi 31-08 sur la protection du consommateur (regles publicitaires)",
        "source_url": "https://www.onssa.gov.ma/wp-content/uploads/2022/06/Reglementation/C.Reglementation-Connexe/4.%20Divers/LOI.31-08.FR.pdf",
        "allowed_roles": ["tous", "marketing", "direction"],
        "pages": [
            """REGLES DE PUBLICITE ET COMMUNICATION COMMERCIALE AU MAROC
Source : Loi n 31-08 edictant des mesures de protection du consommateur, promulguee par le Dahir n 1.11.03 du 18 fevrier 2011.

La loi 31-08 encadre notamment la publicite destinee aux consommateurs marocains. Elle interdit toute publicite comportant des allegations, indications ou presentations fausses ou de nature a induire le consommateur en erreur, quelle que soit la forme du message publicitaire.

Le texte impose une information appropriee et claire du consommateur sur les produits, biens ou services proposes, ainsi que sur les caracteristiques du financement lorsque celui-ci est mentionne dans une publicite ecrite - cette information doit s'inscrire dans le corps principal du texte publicitaire, pas en petits caracteres secondaires.

Les loteries publicitaires (operations proposees au public faisant naitre l'esperance d'un gain, quelles que soient les modalites de tirage au sort) sont specifiquement definies et encadrees par la loi, quelle que soit la denomination commerciale utilisee pour les designer.""",
            """CLAUSES ABUSIVES ET CONTRATS DE CONSOMMATION - LOI 31-08

La loi 31-08 protege le consommateur contre les clauses abusives dans les contrats de consommation, notamment celles relatives aux services financiers, credits a la consommation, credits immobiliers, publicite, ventes a distance et demarchage. Toute clause abusive est nulle et de nul effet ; le contrat reste applicable dans ses autres dispositions si celles-ci peuvent subsister sans la clause abusive concernee.

Est egalement repute nul tout engagement resultant d'un abus de la faiblesse ou de l'ignorance du consommateur, celui-ci conservant le droit de se faire rembourser les sommes deja versees. La loi prevoit enfin des garanties legales et contractuelles concernant les defauts de la chose vendue et le service apres-vente, avec des procedures d'indemnisation en cas de prejudice subi par le consommateur."""],
    },
}


def process_department(dept_key: str, dept_data: dict):
    print(f"Generation : {dept_key} - source reelle : {dept_data['fichier_source']}")

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
        "source_url": dept_data["source_url"],
        "nb_pages_total": len(dept_data["pages"]),
        "nb_pages_low_text": 0,
        "pages_low_text": [],
        "nb_chunks": len(chunks),
        "allowed_roles": dept_data["allowed_roles"],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "is_synthetic": False,  # <-- donnee REELLE, basee sur de vraies lois marocaines
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

    print("\nTermine. Ces documents sont bases sur de VRAIES lois marocaines publiques,")
    print("pas sur du contenu invente. Sources citees dans chaque fichier _chunks.json.")
    print("Prochaine etape : supprime les anciens documents synthetiques (Entreprise_Demo_SA)")
    print("puis relance build_index.py pour reconstruire l'index avec ce contenu reel.")


if __name__ == "__main__":
    main()