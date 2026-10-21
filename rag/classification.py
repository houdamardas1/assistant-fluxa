"""Classification des documents et habilitation des profils.

Un profil lit un passage si le controle par departement/entreprise l'autorise
ET si son habilitation est superieure ou egale a la classification du document.
Table volontairement dans le code : elle survit a une reconstruction de l'index.
"""

NIVEAUX = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED")
RANG = {n: i for i, n in enumerate(NIVEAUX)}

# Politique de demonstration appliquee a des documents reels deja publics :
# le niveau exprime la politique de diffusion de la plateforme, pas une
# propriete du document.
CLASSIFICATION_DOCUMENTS = {
    "Code_de_Commerce_Loi_15-95.pdf": "PUBLIC",
    "Code_Obligations_Contrats_DOC.pdf": "PUBLIC",
    "Loi_31-08_Protection_Consommateur.pdf": "PUBLIC",
    "Code_du_Travail_Loi_65-99.pdf": "PUBLIC",
    "DNSSI_Directive_Securite_SI.pdf": "PUBLIC",
    "UNIMER_RFA_2024.pdf": "INTERNAL",
    "Auto_Nejma_RFA_2023.pdf": "INTERNAL",
    "Wafa_Assurance_RFA_2025.pdf": "CONFIDENTIAL",
    "CDG_Capital_RFA_2024.pdf": "CONFIDENTIAL",
}

# Document non classe : INTERNAL (jamais PUBLIC par defaut).
CLASSIFICATION_PAR_DEFAUT = "INTERNAL"

HABILITATIONS = {
    "tous": "RESTRICTED",
    "direction": "RESTRICTED",
    "finance": "CONFIDENTIAL",
    "juridique": "CONFIDENTIAL",
    "rh": "CONFIDENTIAL",
    "it": "CONFIDENTIAL",
    "commerce": "INTERNAL",
    "marketing": "INTERNAL",
}


def niveau_du_fichier(fichier_source) -> str:
    return CLASSIFICATION_DOCUMENTS.get(fichier_source or "", CLASSIFICATION_PAR_DEFAUT)


def niveau_du_chunk(chunk: dict) -> str:
    """Champ explicite "classification" du chunk s'il est valide, sinon la table."""
    explicite = chunk.get("classification")
    if explicite in RANG:
        return explicite
    return niveau_du_fichier(chunk.get("fichier_source"))


def habilitation_du_role(role: str) -> str:
    return HABILITATIONS.get(role, "PUBLIC")


def habilitation_suffisante(role: str, niveau: str) -> bool:
    return RANG[habilitation_du_role(role)] >= RANG.get(niveau, RANG[CLASSIFICATION_PAR_DEFAUT])
