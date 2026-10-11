"""Recherche hybride FAISS + lexical, rescue metier, chargement de l'index et reclassement des candidats."""

import json
import re
from collections import Counter
import faiss

from .config import (
    BONUS_ARTICLE_TITRE,
    DEBUG,
    INDEX_DIR,
    POIDS_FAISS,
    POIDS_LEXICAL,
    TOP_K_RETRIEVAL,
    TOP_K_VERIFY,
    _dbg,
)
from .finance import (
    _RE_DEVISES,
    _RE_FILIALES,
    _preuve_metric_locale,
    detect_chunk_scope,
    detect_famille,
    detect_metric,
    detect_scope,
    metriques_presentes,
    terme_generique_present,
    terme_sectoriel_present,
    termes_generiques_famille,
    termes_sectoriels_famille,
)
from .juridique import (
    detect_reference_article,
    est_renvoi_article,
    est_titre_article,
)
from .rbac import (
    chunk_matches_department,
    detect_entreprises,
    est_accessible,
)
from .temporel import classify_chunk_temporal, detect_temporal_requirement
from .textutils import _norm, contient_un_des_termes, mots_utiles, position_terme


def load_index():
    index = faiss.read_index(str(INDEX_DIR / "index.faiss"))

    with open(INDEX_DIR / "metadata.json", "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return index, metadata


def score_lexical(
    query_words: list,
    annees: list,
    famille: str | None,
    content: str,
    numero_article: str | None = None,
    secteur=None,
) -> float:
    """Score lexical dans [0, 1]."""
    if not query_words and not numero_article:
        return 0.0

    content_lower = content.lower()

    matches = sum(
        1 for w in query_words if re.search(rf"\b{re.escape(w)}\b", content_lower)
    )
    ratio = matches / len(query_words) if query_words else 0.0

    bonus_annee = (
        1.0
        if any(re.search(rf"\b{re.escape(a)}\b", content) for a in annees)
        else 0.0
    )

    if terme_generique_present(famille, content):
        bonus_phrase = 1.0
    elif terme_sectoriel_present(famille, secteur, content):
        bonus_phrase = 0.6
    else:
        bonus_phrase = 0.0

    bonus_article = 0.0

    if numero_article:
        if est_titre_article(content, numero_article):
            bonus_article = 1.0
        elif est_renvoi_article(content, numero_article):
            bonus_article = 0.25

    return min(
        1.0,
        ratio * 0.40
        + bonus_annee * 0.05
        + bonus_phrase * 0.35
        + bonus_article * 0.20,
    )


def search(
    query: str,
    model,
    index,
    metadata,
    user_role: str,
    top_k: int = TOP_K_RETRIEVAL,
    selected_department: str | None = None,
):
    """Recherche hybride FAISS + lexical, avec rescue metier.

    Ordre des filtres : controle d'acces (est_accessible) PUIS perimetre
    (departement, entreprise nommee). Le departement est un filtre de
    perimetre ; la securite reste portee par est_accessible().
    """
    query_vec = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_vec)

    scores, indices = index.search(query_vec, index.ntotal)

    faiss_par_idx = {
        int(idx): float(score)
        for score, idx in zip(scores[0], indices[0])
        if idx != -1
    }

    query_words = mots_utiles(query)
    annees = re.findall(r"\b(?:19|20)\d{2}\b", query)
    famille = detect_famille(query)
    metric_demande = detect_metric(query)
    numero_article = detect_reference_article(query)
    requested_year, temporal_mode = detect_temporal_requirement(query)

    noms_connus = {c.get("entreprise") for c in metadata if c.get("entreprise")}
    entreprises_visees = detect_entreprises(query, noms_connus)

    resultats = []
    vus = set()
    pool_metrique, pool_generique, pool_sectoriel, pool_temporel = [], [], [], []

    for idx, chunk in enumerate(metadata):

        if not est_accessible(chunk, user_role):
            continue

        type_document = chunk.get("type_document", "entreprise")
        est_reglementaire = type_document == "public_reglementaire"

        if (
            selected_department
            and not est_reglementaire
            and not chunk_matches_department(chunk, selected_department)
        ):
            continue

        if (
            entreprises_visees
            and not est_reglementaire
            and chunk.get("entreprise") not in entreprises_visees
        ):
            continue

        content = chunk.get("content", "")

        if not content:
            continue

        cle = (chunk.get("fichier_source"), chunk.get("page"), content[:120])

        if cle in vus:
            continue

        vus.add(cle)

        s_faiss = faiss_par_idx.get(idx, 0.0)

        s_lex = score_lexical(
            query_words, annees, famille, content,
            numero_article=numero_article, secteur=chunk.get("secteur"),
        )

        hybride = POIDS_FAISS * s_faiss + POIDS_LEXICAL * s_lex

        article_titre = (
            est_titre_article(content, numero_article) if numero_article else False
        )

        est_generique = terme_generique_present(famille, content)
        est_sectoriel = (
            not est_generique
            and terme_sectoriel_present(famille, chunk.get("secteur"), content)
        )
        a_terme_metier = est_generique or est_sectoriel

        if hybride < 0.20 and not article_titre and not a_terme_metier:
            continue

        if s_lex > s_faiss + 0.15:
            origine = "lexical"
        elif s_faiss > s_lex + 0.15:
            origine = "faiss"
        else:
            origine = "hybride"

        temporal_status = classify_chunk_temporal(chunk, requested_year)

        resultat = {
            "score": hybride,
            "entreprise": chunk.get("entreprise"),
            "secteur": chunk.get("secteur"),
            "page": chunk.get("page"),
            "fichier_source": chunk.get("fichier_source"),
            "content": content,
            "is_synthetic": chunk.get("is_synthetic", False),
            "type_document": type_document,
            "departement": chunk.get("departement"),
            "departements": chunk.get("departements"),
            "_source": origine,
            "_faiss_score": s_faiss,
            "_lexical_score": s_lex,
            "_article_titre": article_titre,
            "_terme_metier": a_terme_metier,
            "_terme_generique": est_generique,
            "_terme_sectoriel": est_sectoriel,
            "_scope": detect_chunk_scope(content),
            "_temporal_status": temporal_status,
        }

        resultats.append(resultat)

        if requested_year is not None and (
            (temporal_mode == "actual" and temporal_status == "actual")
            or (temporal_mode == "planned"
                and temporal_status in {"actual", "planned"})
        ):
            pool_temporel.append(resultat)

        # Pools de rescue : chunks d'entreprise uniquement (un texte de loi
        # qui cite incidemment "chiffre d'affaires" ne repond jamais a une
        # question sur une entreprise et evincerait la vraie donnee).
        if not est_reglementaire:

            if metric_demande and _preuve_metric_locale(content, metric_demande):
                pool_metrique.append(resultat)

            if est_generique:
                pool_generique.append(resultat)
            elif est_sectoriel:
                pool_sectoriel.append(resultat)

    resultats.sort(key=lambda r: r["score"], reverse=True)

    limite = top_k + 10
    top_resultats = resultats[:limite]
    max_rescue = 10

    pools = []

    if pool_temporel:
        pools.append(("temporel", pool_temporel))
    if metric_demande:
        # Priorite a la metrique LITTERALE, avant les pools de famille.
        pools.append(("metrique", pool_metrique))
    pools.append(("generique", pool_generique))
    pools.append(("sectoriel", pool_sectoriel))

    if any(pool for _, pool in pools):

        cles_top = {
            (r["fichier_source"], r["page"], r["content"][:120])
            for r in top_resultats
        }
        injectes = 0

        for niveau, pool in pools:

            if injectes >= max_rescue:
                break

            hors_top = sorted(
                (
                    r for r in pool
                    if (r["fichier_source"], r["page"], r["content"][:120])
                    not in cles_top
                ),
                key=lambda r: r["score"],
                reverse=True,
            )

            for r in hors_top:

                if injectes >= max_rescue:
                    break

                if len(top_resultats) >= limite:
                    # Ne jamais ejecter un chunk qui porte la preuve de la
                    # metrique demandee.
                    for i in range(len(top_resultats) - 1, -1, -1):
                        if not (
                            metric_demande
                            and _preuve_metric_locale(
                                top_resultats[i].get("content", ""),
                                metric_demande,
                            )
                        ):
                            top_resultats.pop(i)
                            break

                top_resultats.append(r)
                cles_top.add((r["fichier_source"], r["page"], r["content"][:120]))
                injectes += 1

                _dbg(
                    f"Rescue ({niveau}) : {r.get('fichier_source')} "
                    f"p.{r.get('page')} score={r.get('score', 0):.3f}"
                )

    return top_resultats


_RE_CA_SOUS_PERIMETRE = re.compile(
    r"""
    \bchiffre\s+d['’]?\s*affaires\s+
        (?: de\s+la\s+filiale
          | des?\s+filiales
          | de\s+l['’]?\s*activit[ée]s?
          | (?:TPME|TPE|PME)
          | (?:RDS|risques?\s+divers)
          | par\s+(?:activit[ée]|branche|segment|m[ée]tier) )
    | \b(?:TPME|TPE|PME|RDS)\b .*? \bchiffre\s+d['’]?\s*affaires
    | \brisques?\s+divers\b .*? \bchiffre\s+d['’]?\s*affaires
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


_RE_VALEUR_PROCHE = re.compile(
    r"\d[\d\s.,]*\s*(?:mmdh|mdh|mmad|kmad|mad|dh|dirhams?|millions?|milliards?)",
    flags=re.IGNORECASE,
)


def select_best_candidates(
    query: str, results: list, top_n: int = TOP_K_VERIFY
) -> list:
    """Reclasse les resultats (score de reclassement stocke dans
    r["_score_reclasse"], r["score"] reste le score de retrieval brut) et
    selectionne les top_n candidats a verifier."""
    if not results:
        return []

    famille = detect_famille(query)
    scope_demande = detect_scope(query)
    metric_demande = detect_metric(query)
    demande_filiale = bool(_RE_FILIALES.search(_norm(query)))
    requested_year, temporal_mode = detect_temporal_requirement(query)

    scored = []

    for r in results:
        content = r.get("content", "")
        content_norm = _norm(content)
        bonus = 0.0

        # 1. Titre d'article
        if r.get("_article_titre"):
            bonus += BONUS_ARTICLE_TITRE

        # 2-3. Terme metier generique / sectoriel
        termes_niveau = termes_generiques_famille(famille)
        est_generique = contient_un_des_termes(content, termes_niveau)
        est_sectoriel = False

        if not est_generique:
            termes_niveau = termes_sectoriels_famille(famille, r.get("secteur"))
            est_sectoriel = contient_un_des_termes(content, termes_niveau)

        if est_generique:
            bonus += 0.45
        elif est_sectoriel:
            bonus += 0.20

        # 4. Terme metier proche d'une valeur
        if est_generique or est_sectoriel:
            for t in termes_niveau:
                m = position_terme(content, t)
                if m is None:
                    continue
                fenetre = content[max(0, m.start() - 250):m.start() + 500]
                if _RE_VALEUR_PROCHE.search(fenetre):
                    bonus += 0.20
                    break

        # 5. Perimetre comptable
        scope_chunk = detect_chunk_scope(content)
        r["_scope"] = scope_chunk

        if scope_demande and scope_chunk:
            bonus += 0.30 if scope_chunk == scope_demande else -0.35

        # 6. Filiales / devises etrangeres
        if not demande_filiale and scope_chunk != "consolide":
            if _RE_FILIALES.search(content_norm):
                bonus -= 0.30
            if _RE_DEVISES.search(content_norm):
                bonus -= 0.25

        # 7. Metrique litterale
        r["_preuve_metric"] = False
        r["_ca_sous_perimetre"] = False

        if metric_demande:
            preuve = _preuve_metric_locale(content, metric_demande)
            r["_preuve_metric"] = preuve

            if preuve:
                bonus += 0.40
            elif metric_demande in metriques_presentes(content):
                bonus -= 0.10
            else:
                bonus -= 0.45

            if metric_demande == "chiffre_affaires":
                if _RE_CA_SOUS_PERIMETRE.search(content):
                    r["_ca_sous_perimetre"] = True
                    bonus -= 0.65
                else:
                    bonus += 0.20

        # 8. Temporalite
        temporal_status = (
            classify_chunk_temporal(r, requested_year) if requested_year else "unknown"
        )
        r["_temporal_status"] = temporal_status

        if requested_year:
            if temporal_mode == "actual":
                bonus += {"actual": 0.55, "planned": -0.65}.get(temporal_status, -0.20)
            elif temporal_mode == "planned":
                bonus += {"planned": 0.40, "actual": 0.15}.get(temporal_status, 0.0)

        score_final = r.get("score", 0.0) + bonus
        r["_score_reclasse"] = score_final
        scored.append((score_final, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    if DEBUG:
        for rang, (s, r) in enumerate(scored[:10], start=1):
            print(
                f"[DEBUG] reclassement #{rang} : {s:.3f} "
                f"(retrieval={r.get('score', 0):.3f}) p.{r.get('page')} "
                f"scope={r.get('_scope')} preuve_metric={r.get('_preuve_metric')} "
                f"ca_sous_perimetre={r.get('_ca_sous_perimetre')}"
            )

    # Selection : preuve de la metrique d'abord, puis meilleurs scores,
    # puis filet de securite sans limite par page. Un CA de sous-perimetre
    # n'est JAMAIS selectionne.
    max_per_page = 2
    selected, deja, page_counts = [], set(), Counter()

    def ajouter(r, limite_page=True):
        if metric_demande == "chiffre_affaires" and r.get("_ca_sous_perimetre"):
            return

        cle = (r["fichier_source"], r["page"], r["content"][:100])
        cle_page = (r["fichier_source"], r["page"])

        if cle in deja:
            return
        if limite_page and page_counts[cle_page] >= max_per_page:
            return

        selected.append(r)
        deja.add(cle)
        page_counts[cle_page] += 1

    if metric_demande:
        for _, r in scored:
            if len(selected) >= top_n:
                break
            if r.get("_preuve_metric"):
                ajouter(r)

    for _, r in scored:
        if len(selected) >= top_n:
            break
        ajouter(r)

    for _, r in scored:
        if len(selected) >= top_n:
            break
        ajouter(r, limite_page=False)

    return selected
