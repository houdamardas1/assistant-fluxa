"""Detection automatique du departement (mots-cles puis repli par embeddings)."""

import re
import faiss

from .config import (
    MARGE_EMBEDDING_DEPARTEMENT,
    SEUIL_DETECTION_DEPARTEMENT,
    SEUIL_EMBEDDING_DEPARTEMENT,
    _dbg,
)
from .textutils import _norm


# Mots-cles par departement : (regex SANS accents, poids). Poids 2 = signal
# fort ; poids 1 = signal faible (ne suffit pas seul, voir
# SEUIL_DETECTION_DEPARTEMENT).
_MOTS_CLES_DEPARTEMENT = {
    "finance": [
        (r"chiffres? d'affaires", 2), (r"resultats? net", 2),
        (r"bilans?", 2), (r"dividendes?", 2), (r"rnpg", 2),
        (r"primes? (?:emises?|acquises?|brutes?)", 2),
        (r"revenus? d'assurance", 2),
        (r"produits? des activites d'assurance", 2),
        (r"resultats? (?:sociaux|consolides?)", 2),
        (r"comptes? (?:sociaux|consolides?)", 2),
        (r"etats? financiers?", 2), (r"fonds propres", 2),
        (r"tresorerie", 2), (r"rentabilite", 2),
        (r"resultat (?:de la )?(?:non[- ])?vie", 2),
        (r"budgets?", 1), (r"charges?", 1), (r"marges?", 1),
        (r"comptabilite", 1), (r"investissements?", 1),
    ],
    "direction": [
        (r"conseil d'administration", 2), (r"conseil de surveillance", 2),
        (r"assemblee generale", 2), (r"administrateurs?", 2),
        (r"directeur general", 2), (r"directrice generale", 2),
        (r"comite de direction", 2), (r"comite d'audit", 2),
        (r"comex", 2), (r"plan strategique", 2),
        (r"orientations? strategiques?", 2), (r"gouvernance", 2),
        (r"strategie", 1), (r"rse", 1), (r"esg", 1),
    ],
    "it": [
        (r"securite informatique", 2), (r"politique de securite", 2),
        (r"directive de securite", 2), (r"dnssi", 2),
        (r"systemes? d'information", 2), (r"cybersecurite", 2),
        (r"mots? de passe", 2), (r"serveurs?", 2), (r"sauvegardes?", 2),
        (r"incidents? de securite", 2), (r"infrastructure", 2),
        (r"reseau informatique", 2),
        (r"securite", 1), (r"logiciels?", 1), (r"application", 1),
    ],
    "rh": [
        (r"conges? (?:annuels?|payes?)", 2), (r"salaires?", 2),
        (r"recrutements?", 2), (r"code du travail", 2),
        (r"reglement interieur", 2), (r"contrats? de travail", 2),
        (r"paie", 2), (r"licenciements?", 2), (r"demissions?", 2),
        (r"remunerations?", 2), (r"ressources humaines", 2),
        (r"periode d'essai", 2),
        (r"formations?", 1), (r"collaborateurs?", 1), (r"salaries?", 1),
        (r"employes?", 1), (r"absences?", 1),
    ],
    "commerce": [
        (r"procedures? commerciales?", 2),
        (r"conditions generales de vente", 2), (r"devis", 2),
        (r"prospects?", 2), (r"offres? commerciales?", 2),
        (r"tarifs?", 2), (r"commandes?", 2), (r"remises?", 2),
        (r"clients?", 1), (r"ventes?", 1),
    ],
    "juridique": [
        (r"contrats? cadres?", 2), (r"clauses? abusives?", 2),
        (r"clause de confidentialite", 2), (r"code de commerce", 2),
        (r"code des obligations", 2), (r"registre du commerce", 2),
        (r"immatriculation", 2), (r"protection des? consommateurs?", 2),
        (r"contrats? de consommation", 2), (r"contentieux", 2),
        (r"conformite juridique", 2), (r"loi \d+-\d+", 2),
        (r"clauses?", 1), (r"lois?", 1), (r"juridique", 1),
        (r"contrats?", 1), (r"articles? \d+", 1),
    ],
    "marketing": [
        (r"charte graphique", 2), (r"charte editoriale", 2),
        (r"campagnes? marketing", 2), (r"reseaux sociaux", 2),
        (r"newsletter", 2), (r"image de marque", 2),
        (r"identite visuelle", 2),
        (r"marketing", 1), (r"communication", 1), (r"marque", 1),
        (r"publicite", 1),
    ],
}


_RE_DEPARTEMENT = {
    dept: [(re.compile(rf"\b(?:{p})\b"), poids) for p, poids in termes]
    for dept, termes in _MOTS_CLES_DEPARTEMENT.items()
}


def detect_department(query: str, user_role: str | None = None) -> str | None:
    """Detecte le departement concerne par la question.

    Score = somme des poids des mots-cles du departement. Retourne None si
    aucun departement n'atteint SEUIL_DETECTION_DEPARTEMENT (aucun filtre
    n'est alors applique). En cas d'egalite, le departement du role de
    l'utilisateur departage ; sinon None.
    """
    q = _norm(query)

    scores = {
        dept: sum(poids for rx, poids in regles if rx.search(q))
        for dept, regles in _RE_DEPARTEMENT.items()
    }

    meilleur = max(scores.values())

    if meilleur < SEUIL_DETECTION_DEPARTEMENT:
        return None

    tetes = [d for d, s in scores.items() if s == meilleur]

    if len(tetes) == 1:
        return tetes[0]

    if user_role in tetes:
        return user_role

    return None


# ----------------------------------------------------------------------------
# Detection de REPLI par embeddings (quand les mots-cles ne suffisent pas)
# ----------------------------------------------------------------------------
#
# Chaque departement est decrit par quelques phrases-types (formulations
# naturelles, sans dependre de mots-cles exacts). La question est comparee
# a ces phrases avec le MEME modele d'embeddings que le retrieval (aucun
# modele supplementaire). Le departement n'est retenu que si :
#   - la meilleure similarite atteint SEUIL_EMBEDDING_DEPARTEMENT ;
#   - l'ecart avec le 2e departement atteint MARGE_EMBEDDING_DEPARTEMENT
#     (sinon la question est ambigue : on prefere ne rien detecter).
# Cette detection ne sert QUE de perimetre/contexte : la securite reste
# portee par effective_allowed_roles() sur chaque chunk.

_PHRASES_DEPARTEMENT = {
    "finance": [
        "Quel est le chiffre d'affaires et le résultat net de l'entreprise ?",
        "Quels sont les états financiers, le bilan et la trésorerie ?",
        "Comment évolue la rentabilité, les marges et les dividendes ?",
        "Quel est le budget prévu et le niveau des charges ?",
    ],
    "direction": [
        "Quelles sont les orientations stratégiques décidées par la direction générale ?",
        "Que dit le conseil d'administration sur la gouvernance de l'entreprise ?",
        "Quelles décisions ont été prises en comité de direction ?",
        "Quel est le plan stratégique et la vision du groupe ?",
    ],
    "it": [
        "Quelle est la politique de sécurité informatique de l'entreprise ?",
        "Comment fonctionne le système d'information, les serveurs et les sauvegardes ?",
        "Que faire en cas d'incident de sécurité ou de panne du réseau ?",
        "Comment gérer les accès, les mots de passe et les logiciels ?",
    ],
    "rh": [
        "Combien de jours de congé ai-je le droit de prendre ?",
        "Comment se déroule le recrutement, la paie et la rémunération des salariés ?",
        "Quelles sont les règles du contrat de travail, de la période d'essai et des absences ?",
        "Quelles formations et quels avantages sont offerts aux collaborateurs ?",
    ],
    "commerce": [
        "Quelle est la procédure pour établir un devis ou traiter une commande client ?",
        "Quelles sont les conditions de vente, les tarifs et les remises accordées ?",
        "Comment suivre les prospects et les offres commerciales ?",
        "Comment fidéliser les clients et développer les ventes ?",
    ],
    "juridique": [
        "Que prévoit la loi ou le code concernant les obligations de l'entreprise ?",
        "Quelles clauses du contrat sont abusives ou nécessitent une validation juridique ?",
        "Quelle est la réglementation applicable en cas de litige ou de contentieux ?",
        "Quelles sont les obligations de conformité et de confidentialité ?",
    ],
    "marketing": [
        "Quelle est la charte graphique et l'identité visuelle de la marque ?",
        "Comment préparer une campagne de communication ou de publicité ?",
        "Que publier sur les réseaux sociaux et dans la newsletter ?",
        "Comment renforcer l'image de marque et la notoriété de l'entreprise ?",
    ],
}


# Cache : (matrice normalisee des phrases, departement de chaque ligne).
_CACHE_PROTOTYPES: dict = {}


def _prototypes_departement(model):
    """Embeddings normalises des phrases-types, calcules une seule fois
    par modele."""
    cle = id(model)
    cache = _CACHE_PROTOTYPES.get(cle)

    if cache is not None:
        return cache

    phrases, depts = [], []

    for dept, liste in _PHRASES_DEPARTEMENT.items():
        for p in liste:
            phrases.append(p)
            depts.append(dept)

    matrice = model.encode(phrases, convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(matrice)

    _CACHE_PROTOTYPES[cle] = (matrice, depts)
    return _CACHE_PROTOTYPES[cle]


def detect_department_embeddings(
    query: str, model, user_role: str | None = None
) -> str | None:
    """Detection de repli : departement le plus proche de la question par
    similarite d'embeddings, ou None si le signal est trop faible ou
    ambigu. N'est appelee que lorsque detect_department() ne trouve rien."""
    if not query or not query.strip():
        return None

    matrice, depts = _prototypes_departement(model)

    q_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(q_vec)

    sims = matrice @ q_vec[0]

    # Meilleure similarite par departement.
    par_dept: dict = {}
    for dept, s in zip(depts, sims):
        par_dept[dept] = max(par_dept.get(dept, -1.0), float(s))

    classement = sorted(par_dept.items(), key=lambda x: x[1], reverse=True)
    meilleur_dept, meilleur_score = classement[0]
    second_score = classement[1][1] if len(classement) > 1 else -1.0

    _dbg(
        "Embeddings departement : "
        + ", ".join(f"{d}={s:.2f}" for d, s in classement[:3])
    )

    if meilleur_score < SEUIL_EMBEDDING_DEPARTEMENT:
        return None

    if meilleur_score - second_score < MARGE_EMBEDDING_DEPARTEMENT:
        # Ambigu : le departement du role departage s'il est dans la marge.
        proches = [
            d for d, s in classement
            if meilleur_score - s < MARGE_EMBEDDING_DEPARTEMENT
        ]
        if user_role in proches:
            return user_role
        return None

    return meilleur_dept
