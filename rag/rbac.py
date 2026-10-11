"""Controle d'acces : roles effectifs par chunk, departements autorises, restriction RBAC, entreprises nommees."""

import re
import faiss

from .config import (
    ALIAS_ENTREPRISES,
    ALLOW_PUBLIC_ONLY_DEPARTMENTS,
    DEPARTEMENTS,
    DEPARTMENT_ACCESS_ROLES,
    FICHIERS_TRANSVERSES,
    RBAC_POLICY,
    _dbg,
)


def effective_allowed_roles(chunk: dict) -> set:
    """Roles autorises a lire un chunk (RBAC strict : les textes
    reglementaires suivent les memes regles que les documents d'entreprise).

    Priorite : "access_roles" explicite du chunk > politique par
    DEPARTEMENT > politique par ENTREPRISE > allowed_roles historiques.
    Ne lit JAMAIS le champ "departements" (pertinence d'onglet, pas droit).

    Cas particulier : les fichiers TRANSVERSES (FICHIERS_TRANSVERSES),
    qu'un seul departement ne peut pas couvrir, sont accessibles a tous
    les departements listes plus "direction" et "tous". C'est un correctif
    d'ingestion : a retirer quand le champ "departements" (liste) sera pose.
    """
    transverse = FICHIERS_TRANSVERSES.get(chunk.get("fichier_source"))
    if transverse:
        return set(transverse) | {"direction", "tous"}

    access_roles = chunk.get("access_roles")
    if access_roles:
        return set(access_roles)

    departement = chunk.get("departement")
    if departement in DEPARTMENT_ACCESS_ROLES:
        return set(DEPARTMENT_ACCESS_ROLES[departement])

    ent = chunk.get("entreprise")
    if ent in RBAC_POLICY:
        return set(RBAC_POLICY[ent])

    return set(chunk.get("allowed_roles", []))


def est_accessible(chunk: dict, user_role: str) -> bool:
    return user_role in effective_allowed_roles(chunk)


def user_allowed_departments(user_role: str) -> set:
    """Departements sur lesquels ce role peut poser des questions.
    "tous" et "direction" : vue transverse ; un role departemental : son
    propre departement. Ce n'est pas un second systeme RBAC : chaque chunk
    reste soumis a effective_allowed_roles()."""
    if user_role in ("tous", "direction"):
        return set(DEPARTEMENTS)

    if user_role in DEPARTEMENTS:
        return {user_role}

    return set()


def department_access_denied(user_role: str, departement: str | None) -> bool:
    if not departement or departement not in DEPARTEMENTS:
        return False
    return departement not in user_allowed_departments(user_role)


def departements_du_chunk(chunk: dict) -> set:
    """Departements auxquels un chunk est rattache ("departements" multi,
    puis "departement"). Sert au perimetre d'onglet, pas au controle
    d'acces."""
    deps = chunk.get("departements")

    if isinstance(deps, list) and deps:
        valides = {d for d in deps if d in DEPARTEMENTS}
        if valides:
            return valides

    dep = chunk.get("departement")
    return {dep} if dep in DEPARTEMENTS else set()


def chunk_matches_department(chunk: dict, departement: str) -> bool:
    """Filtre de PERIMETRE (pas d'autorisation). Les textes reglementaires
    restent visibles partout ; un chunk d'entreprise non classifie est
    rattache par convention a Finance et Direction."""
    if chunk.get("type_document", "entreprise") == "public_reglementaire":
        return True

    deps = departements_du_chunk(chunk)

    if deps:
        return departement in deps

    if departement in ("finance", "direction"):
        return chunk.get("type_document", "entreprise") == "entreprise"

    return False


def departement_a_corpus_reel(metadata: list, dept: str) -> bool:
    """Au moins un document REEL du departement : ni synthetique, ni texte
    reglementaire (sauf RAG_ALLOW_PUBLIC_ONLY_DEPARTMENTS=1)."""
    for chunk in metadata:
        if dept not in departements_du_chunk(chunk):
            continue
        if chunk.get("is_synthetic"):
            continue
        if (
            not ALLOW_PUBLIC_ONLY_DEPARTMENTS
            and chunk.get("type_document", "entreprise") == "public_reglementaire"
        ):
            continue
        return True
    return False


def detect_entreprises(query: str, noms_connus: set) -> set:
    """Entreprises explicitement nommees dans la question (frontieres de
    mots)."""
    q = query.lower()
    trouvees = set()

    for nom in noms_connus:
        variantes = {
            nom.lower(),
            nom.lower().replace("_", " "),
            nom.lower().replace("_", "-"),
        }
        if any(re.search(rf"\b{re.escape(v)}\b", q) for v in variantes):
            trouvees.add(nom)

    for alias, canonique in ALIAS_ENTREPRISES.items():
        if re.search(rf"\b{re.escape(alias)}\b", q) and canonique in noms_connus:
            trouvees.add(canonique)

    return trouvees


def search_without_rbac(query: str, model, index, metadata, top_k: int = 10):
    """Recherche FAISS sans filtre RBAC, uniquement pour distinguer
    "information absente" de "information existante mais non autorisee"
    (voir check_rbac_restriction)."""
    query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_vec)

    scores, indices = index.search(query_vec, index.ntotal)

    noms_connus = {c.get("entreprise") for c in metadata if c.get("entreprise")}
    entreprises_visees = detect_entreprises(query, noms_connus)

    resultats = []

    for score, idx in zip(scores[0], indices[0]):

        if idx == -1:
            continue

        chunk = metadata[idx]

        if entreprises_visees and chunk.get("entreprise") not in entreprises_visees:
            continue

        resultats.append({
            "score": float(score),
            "entreprise": chunk.get("entreprise"),
            "secteur": chunk.get("secteur"),
            "page": chunk.get("page"),
            "fichier_source": chunk.get("fichier_source"),
            "allowed_roles": sorted(effective_allowed_roles(chunk)),
            # Champs lus par effective_allowed_roles() : sans eux, le calcul
            # retomberait sur RBAC_POLICY seule (faux HORS_PERIMETRE).
            "access_roles": chunk.get("access_roles"),
            "departement": chunk.get("departement"),
            "type_document": chunk.get("type_document", "entreprise"),
        })

        if len(resultats) >= top_k:
            break

    return resultats


def check_rbac_restriction(
    query: str, model, index, metadata, user_role: str, authorized_results: list
) -> bool:
    """Vrai si des documents pertinents existent mais ne sont pas
    autorises pour ce role."""
    public_threshold = 0.55

    if authorized_results:

        if authorized_results[0].get("_faiss_score", 0.0) >= 0.72:
            return False

        for r in authorized_results:
            if (
                r.get("type_document") == "public_reglementaire"
                and r.get("score", 0) >= public_threshold
            ):
                return False

    tous = search_without_rbac(query, model, index, metadata, top_k=10)

    if not tous:
        return False

    # Pages (fichier, page) que ce role peut lire par au moins un chunk : un
    # doublon interdit de la meme page (ex : meme texte ingere dans deux
    # departements) ne constitue pas une restriction reelle.
    pages_accessibles = {
        (c.get("fichier_source"), c.get("page"))
        for c in metadata
        if est_accessible(c, user_role)
    }

    interdits = [
        r for r in tous
        if r["score"] >= 0.5
        and user_role not in effective_allowed_roles(r)
        and (r.get("fichier_source"), r.get("page")) not in pages_accessibles
    ]

    if interdits:
        _dbg(
            f"RBAC : {len(interdits)} chunk(s) pertinent(s) interdit(s) pour "
            f"{user_role!r} : "
            + "; ".join(
                f"{r.get('fichier_source')} p.{r.get('page')} "
                f"dept={r.get('departement')!r} score={r['score']:.2f}"
                for r in interdits[:5]
            )
        )

    if len(interdits) >= 2:
        return True

    if len(interdits) == 1 and interdits[0]["score"] >= 0.6:
        meilleur_autorise = (
            authorized_results[0].get("_faiss_score", 0.0)
            if authorized_results else 0.0
        )
        return interdits[0]["score"] > meilleur_autorise + 0.1

    return False
