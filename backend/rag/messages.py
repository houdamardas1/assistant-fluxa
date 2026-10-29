"""Messages utilisateur (absence, departement vide, clarification, quota) et refus d'acces."""

from .config import LIBELLE_DEPARTEMENT


MESSAGE_ABSENTE = (
    "Je ne dispose pas actuellement d'informations suffisantes dans les "
    "documents disponibles pour répondre précisément à cette question.\n\n"
    "Afin de garantir une réponse fiable, je préfère ne pas fournir "
    "d'information qui ne pourrait pas être vérifiée."
)


MESSAGE_DEPARTEMENT_VIDE = (
    "Aucun document n'est actuellement indexé pour le département "
    "{dept}.\n\n"
    "Je ne peux donc pas répondre à cette question sans risque "
    "d'inexactitude. Veuillez contacter l'administrateur afin de vérifier "
    "que les documents de ce département ont bien été ingérés."
)


MESSAGE_CLARIFICATION_PERIMETRE = (
    "Précision nécessaire\n\n"
    "Les documents disponibles contiennent à la fois des valeurs sociales "
    "et des valeurs consolidées pour cet indicateur, et ces valeurs sont "
    "différentes.\n\n"
    "Souhaitez-vous le périmètre social ou le périmètre consolidé ? "
    "Reformulez votre question en le précisant."
)


MESSAGE_QUOTA = (
    "Service momentanément saturé\n\n"
    "Le service de génération a atteint sa limite d'utilisation. "
    "Cela ne signifie pas que l'information est absente des documents. "
    "Veuillez réessayer dans quelques minutes."
)


def message_refus_acces(
    user_role: str,
    departement: str | None = None,
    entreprises: set | None = None,
) -> str:
    """Message professionnel de refus d'acces, adapte a la situation :
    documents d'une entreprise nommee (prioritaire), departement detecte,
    ou perimetre restreint non precise."""
    profil = LIBELLE_DEPARTEMENT.get(user_role)
    profil_txt = f"votre profil actuel ({profil})" if profil else "votre profil actuel"

    if entreprises:
        noms = ", ".join(sorted(e.replace("_", " ") for e in entreprises))
        objet = f"concerne des documents à accès restreint ({noms})"
    elif departement in LIBELLE_DEPARTEMENT:
        objet = f"relève du département {LIBELLE_DEPARTEMENT[departement]}"
    else:
        objet = "relève d'un périmètre à accès restreint"

    return (
        "Accès non autorisé\n\n"
        f"Votre demande {objet}. Compte tenu de {profil_txt}, vous ne "
        "disposez pas des autorisations nécessaires pour consulter ces "
        "informations.\n\n"
        "Si cet accès est nécessaire à votre activité, nous vous invitons "
        "à adresser votre demande au responsable du département concerné "
        "ou à l'administrateur de la plateforme, qui pourra examiner "
        "l'ajustement de vos droits.\n\n"
        "Je reste à votre disposition pour toute question relevant de "
        "votre périmètre."
    )
