"""Pipeline complet : retrieval, RBAC, garde-fous, verification, generation, questions comparatives."""

from .config import (
    DEPARTEMENTS,
    LIBELLE_DEPARTEMENT,
    TOP_K_CONTEXT,
    TOP_K_RETRIEVAL,
    TOP_K_VERIFY,
    _dbg,
)
from .departements import detect_department, detect_department_embeddings
from .finance import (
    _LIBELLE_METRIC,
    _LIBELLE_SCOPE,
    build_subquery,
    detect_chunk_scope,
    detect_intents,
    detect_metric,
    detect_scope,
    extraire_montant_source,
    metric_incompatible,
    scope_incompatible,
)
from .generation import (
    extract_cited_sources,
    generate_answer,
    generate_general_answer,
    renumber_multi_intent_sources,
)
from .intent import PREFIXES_GENERAUX, classify_question, detect_intent
from .kpi import repondre_depuis_kpi
from .messages import (
    MESSAGE_ABSENTE,
    MESSAGE_CLARIFICATION_PERIMETRE,
    MESSAGE_DEPARTEMENT_VIDE,
    message_refus_acces,
)
from .rbac import (
    check_rbac_restriction,
    departement_a_corpus_reel,
    department_access_denied,
    detect_entreprises,
    user_allowed_departments,
)
from .retrieval import search, select_best_candidates
from .temporel import detect_temporal_requirement, temporal_incompatible
from .textutils import _norm
from .postcheck import verifier_fondement
from .verification import verify_relevance


def _resultat(answer: str, mode: str, type_: str, **extra) -> dict:
    """Dictionnaire de resultat avec toutes les cles par defaut."""
    base = {
        "answer": answer,
        "cited_sources": [],
        "all_results": [],
        "candidats_finaux": [],
        "max_score": 0.0,
        "mode": mode,
        "type": type_,
        "can_answer": False,
        "confidence": 0.0,
        "verify_error": False,
        "extraits_verifier": [],
        "incoherence_citation": False,
        "montant_structure": None,
        "departement": None,
    }
    base.update(extra)
    return base


def _pipeline_rag(
    query: str, model, index, metadata, user_role: str, departement: str | None,
    departement_contexte: str | None = None,
) -> dict:
    """Retrieval -> controle RBAC -> reclassement -> garde-fous Python ->
    verification LLM -> generation.

    `departement` sert de FILTRE de perimetre (peut etre None) ;
    `departement_contexte` est le departement detecte, utilise pour adapter
    le vocabulaire de la reponse meme quand aucun filtre n'est applique."""
    ctx_dept = departement_contexte or departement
    fondement = None

    results = search(
        query, model, index, metadata, user_role=user_role,
        top_k=TOP_K_RETRIEVAL, selected_department=departement,
    )
    max_score = max((r.get("score", 0.0) for r in results), default=0.0)

    noms = {c.get("entreprise") for c in metadata if c.get("entreprise")}
    if check_rbac_restriction(
        query, model, index, metadata, user_role, results,
        departement_autorise=(
            ctx_dept if ctx_dept and not department_access_denied(user_role, ctx_dept)
            else None
        ),
        entreprises_nommees=detect_entreprises(query, noms),
    ):
        return _resultat(
            message_refus_acces(
                user_role,
                departement=(
                    ctx_dept if department_access_denied(user_role, ctx_dept)
                    else None
                ),
                entreprises=detect_entreprises(query, noms),
            ),
            "HORS_PERIMETRE", "HORS_PERIMETRE",
            all_results=results, max_score=max_score,
        )

    candidats = select_best_candidates(query, results, top_n=TOP_K_VERIFY)
    avant_filtre = len(candidats)

    # Garde-fous deterministes AVANT le LLM : perimetre, metrique, temporalite.
    candidats = [
        r for r in candidats
        if not (
            scope_incompatible(query, r.get("content", ""))
            or metric_incompatible(query, r.get("content", ""))
            or temporal_incompatible(query, r)
        )
    ]

    _dbg(
        f"Garde-fous : {avant_filtre - len(candidats)} candidat(s) elimine(s) "
        f"(scope={detect_scope(query)!r}, metric={detect_metric(query)!r}, "
        f"temporalite={detect_temporal_requirement(query)!r})."
    )

    # Perimetre non precise alors que social ET consolide existent : on
    # demande lequel plutot que de choisir pour l'utilisateur.
    #
    # Le filtre par ANNEE est applique EN AMONT de ce bloc : `candidats` a
    # deja ete filtre par temporal_incompatible() (annee detectee par
    # detect_temporal_requirement(), qui reconnait 19xx et 20xx). Pour une
    # annee absente des documents (ex : 1999), `candidats` est donc vide et
    # aucune clarification n'est declenchee : la question aboutit a ABSENT.
    if candidats and detect_metric(query) and detect_scope(query) is None:
        perimetres = {
            detect_chunk_scope(r.get("content", "")) for r in candidats
        } - {None}

        if {"social", "consolide"} <= perimetres:
            return _resultat(
                MESSAGE_CLARIFICATION_PERIMETRE, "CLARIFICATION", "CLARIFICATION",
                all_results=results, candidats_finaux=candidats,
                max_score=max_score,
            )

    can_answer, confidence, verify_error, extraits = verify_relevance(query, candidats)

    # Sortie incoherente du verificateur (can_answer sans extrait designe) :
    # echec de verification. Exception : le fallback LOCAL (verify_error)
    # ne designe jamais d'extraits par construction.
    if can_answer and not extraits and not verify_error:
        _dbg("Verificateur incoherent : can_answer=True sans extrait designe.")
        can_answer = False
        confidence = min(confidence, 0.4)

    q_type = classify_question(query, results, can_answer, verify_error)

    rag_results = []
    cited_sources = []
    incoherence_citation = False
    montant_structure = None

    if q_type == "ENTREPRISE":

        if extraits:
            rag_results = [
                candidats[n - 1] for n in sorted(set(extraits))
                if 1 <= n <= len(candidats)
            ]
        else:
            rag_results = candidats[:TOP_K_CONTEXT]

        answer = generate_answer(query, rag_results, user_role, ctx_dept)
        cited_sources = extract_cited_sources(answer, rag_results)
        fondement = verifier_fondement(answer, rag_results)
        _dbg("Fondement : score=%s unites=%d non_citees=%d nombres_non_soutenus=%d lexical=%d" % (
            fondement["score"], fondement["unites"], fondement["non_citees"],
            fondement["nombres_non_soutenus"], fondement["a_verifier_lexical"]))
        for d in fondement["details"]:
            _dbg("  fondement - %s : %s" % (",".join(d["problemes"]), d["texte"][:110]))

        if rag_results and not cited_sources:
            incoherence_citation = True
            confidence = min(confidence, 0.6)

        mode = "RAG"

        if can_answer:
            metric = detect_metric(query)
            m = extraire_montant_source(rag_results, metric)

            if m:
                montant_structure = {
                    "valeur": m[0], "unite": m[1],
                    "scope": detect_scope(query), "metric": metric,
                }

    elif q_type == "ABSENTE":
        answer, mode = MESSAGE_ABSENTE, "ABSENT"

    else:
        answer = generate_general_answer(query, ctx_dept)
        mode = "GENERAL"

    return _resultat(
        answer, mode, q_type,
        cited_sources=cited_sources, all_results=results,
        candidats_finaux=rag_results, max_score=max_score,
        can_answer=can_answer, confidence=confidence,
        verify_error=verify_error, extraits_verifier=extraits,
        incoherence_citation=incoherence_citation,
        fondement=fondement,
        montant_structure=montant_structure,
    )


def process_comparative_question(
    query: str, model, index, metadata, user_role: str,
    selected_department: str | None = None,
) -> dict:
    """Question nommant 2+ indicateurs : une sous-question simple par
    indicateur, chacune passant par process_question_hybride() (donc par
    tous les garde-fous). Une difference n'est calculee que si les deux
    montants sont trouves dans LA MEME unite ; la reponse rappelle toujours
    que ce sont deux indicateurs distincts."""

    intents = detect_intents(query)

    if len(intents) < 2:
        return process_question_hybride(
            query, model, index, metadata, user_role,
            selected_department=selected_department,
        )

    noms_connus = {c.get("entreprise") for c in metadata if c.get("entreprise")}
    entreprises = detect_entreprises(query, noms_connus)
    entreprise_display = (
        sorted(entreprises)[0].replace("_", " ") if entreprises else ""
    )

    sous_reponses = []

    for intent in intents:
        subq = build_subquery(entreprise_display, intent)
        _dbg(f"Question comparative -> sous-question : {subq!r}")

        res = process_question_hybride(
            subq, model, index, metadata, user_role,
            selected_department=selected_department,
        )

        montant = None
        if res.get("type") == "ENTREPRISE" and res.get("can_answer"):
            m = res.get("montant_structure")
            if m:
                montant = (m["valeur"], m["unite"])

        sous_reponses.append(
            {"intent": intent, "subquery": subq, "result": res, "montant": montant}
        )

    cited_sources = renumber_multi_intent_sources(sous_reponses)

    lignes = []

    for sr in sous_reponses:
        intent, res = sr["intent"], sr["result"]
        label = _LIBELLE_METRIC.get(intent["metric"], intent["metric"])
        scope_txt = _LIBELLE_SCOPE.get(intent.get("scope")) or "périmètre non précisé"
        titre = f"{label.capitalize()} ({scope_txt}) :"

        if res.get("type") == "ENTREPRISE" and res.get("can_answer"):
            lignes.append(f"{titre}\n{res['answer']}")
        elif res.get("mode") == "CLARIFICATION":
            lignes.append(
                f"{titre}\nPérimètre à préciser : des valeurs sociales et "
                "consolidées existent pour cet indicateur (précisez « social » "
                "ou « consolidé »)."
            )
        elif res.get("mode") == "HORS_PERIMETRE":
            lignes.append(f"{titre}\n{res['answer']}")
        else:
            lignes.append(
                f"{titre}\nInformation absente ou non vérifiable dans les "
                "documents disponibles pour cet indicateur."
            )

    montants = [sr["montant"] for sr in sous_reponses if sr["montant"]]

    if len(montants) == len(sous_reponses) == 2:
        (v1, u1), (v2, u2) = montants

        if u1 == u2:
            scopes_differents = (
                sous_reponses[0]["intent"].get("scope")
                != sous_reponses[1]["intent"].get("scope")
            )
            diff_txt = (
                f"\n\nDifférence calculée : {abs(v1 - v2):g} {u1}.\n"
                "Attention : il ne s'agit pas d'une comparaison homogène, "
                "car ce sont deux indicateurs comptables distincts"
                + (", avec des périmètres potentiellement différents"
                   if scopes_differents else "")
                + ". Cette différence n'a de sens que si vous comparez "
                "explicitement ces deux notions précises."
            )
        else:
            diff_txt = (
                "\n\nLes deux montants trouvés sont exprimés dans des unités "
                f"différentes ({u1} et {u2}) : aucune différence n'est "
                "calculée afin d'éviter toute erreur d'unité."
            )
    else:
        diff_txt = (
            "\n\nUne différence n'a pas pu être calculée car au moins un des "
            "deux indicateurs n'a pas pu être extrait avec certitude des "
            "documents disponibles."
        )

    return _resultat(
        "\n\n".join(lignes) + diff_txt, "MULTI_INTENT", "MULTI_INTENT",
        cited_sources=cited_sources,
        max_score=max(
            (sr["result"].get("max_score", 0.0) for sr in sous_reponses),
            default=0.0,
        ),
        can_answer=all(sr["result"].get("can_answer") for sr in sous_reponses),
        confidence=min(
            (sr["result"].get("confidence", 0.0) for sr in sous_reponses),
            default=0.0,
        ),
        verify_error=any(sr["result"].get("verify_error") for sr in sous_reponses),
        sous_reponses=sous_reponses,
    )


def process_question_hybride(
    query: str,
    model,
    index,
    metadata,
    user_role: str,
    selected_department: str | None = None,
) -> dict:
    """Point d'entree du pipeline.

    Le departement est DETECTE automatiquement depuis la question
    (detect_department, mots-cles ; puis detect_department_embeddings en
    repli) ; `selected_department` reste accepte comme forcage explicite
    (compatibilite avec un appelant qui fournirait deja un onglet) et
    prime alors sur la detection.

    Etapes :
      1. departement = forcage explicite, sinon detection par mots-cles,
         sinon detection de repli par embeddings ;
      2. question generale -> reponse sans RAG (jamais refusee), sauf si
         un departement a ete detecte par mots-cles (ou force) : le RAG
         est alors tente, et le controle d'acces departement s'applique.
         Les questions de definition ("qu'est-ce que...") restent
         generales ;
      3. departement detecte par mots-cles non autorise pour ce role ->
         refus professionnel AVANT tout retrieval. Un departement trouve
         seulement par le repli embeddings, moins fiable, n'est jamais
         utilise pour refuser : s'il n'est pas autorise, il est ignore et
         le controle d'acces par chunk s'applique seul ;
      4. departement sans corpus reel : refus si explicite ; si detecte
         automatiquement, aucun filtre n'est applique (la detection ne doit
         pas bloquer a tort une question dont la reponse est ailleurs) ;
      5. question multi-indicateurs -> process_comparative_question() ;
      6. pipeline RAG ; si un departement DETECTE ne donne rien (retrieval
         vide), une seconde passe sans filtre de departement est tentee
         (le controle d'acces par chunk s'applique dans les deux cas).
    """

    explicite = selected_department if selected_department in DEPARTEMENTS else None

    if explicite:
        departement, origine_detection = explicite, "force"
    else:
        departement = detect_department(query, user_role)
        origine_detection = "mots-cles"

        if departement is None:
            departement = detect_department_embeddings(query, model, user_role)
            origine_detection = "embeddings"

            # Repli moins fiable : jamais utilise pour REFUSER l'acces.
            if department_access_denied(user_role, departement):
                _dbg(
                    f"Departement {departement!r} (embeddings) hors perimetre "
                    f"du role {user_role!r} : ignore."
                )
                departement = None

    _dbg(
        f"Departement : {departement!r} ({origine_detection}) "
        f"| role={user_role!r}"
    )

    multi = len(detect_intents(query)) >= 2

    est_definition = any(
        _norm(query).strip().startswith(p) for p in PREFIXES_GENERAUX
    )
    force_rag = (
        origine_detection in ("mots-cles", "force")
        and departement is not None
        and not est_definition
    )

    if detect_intent(query) == "generale" and not multi and not force_rag:
        return _resultat(
            generate_general_answer(query, departement), "GENERAL", "GENERALE",
            departement=departement,
        )

    if department_access_denied(user_role, departement):
        _dbg(
            f"Acces departement refuse : role={user_role!r} "
            f"autorises={sorted(user_allowed_departments(user_role))}"
        )
        return _resultat(
            message_refus_acces(user_role, departement=departement),
            "HORS_PERIMETRE", "HORS_PERIMETRE", departement=departement,
        )

    # Departement detecte, conserve pour l'affichage et le vocabulaire de la
    # reponse meme si le filtre de perimetre est desactive ci-dessous.
    departement_detecte = departement

    if departement and not departement_a_corpus_reel(metadata, departement):

        if explicite:
            return _resultat(
                MESSAGE_DEPARTEMENT_VIDE.format(
                    dept=LIBELLE_DEPARTEMENT[departement]
                ),
                "ABSENT", "ABSENTE", departement=departement,
            )

        _dbg(f"Departement detecte {departement!r} sans corpus reel : pas de filtre.")
        departement = None

    # Raccourci KPI : chiffre verifie de la table, sans appel au LLM. Ne repond
    # que si la question designe sans ambiguite UN KPI, si le role est autorise
    # et si la valeur figure dans le passage cite ; sinon rend la main.
    if not multi:
        rep_kpi = repondre_depuis_kpi(query, user_role, metadata)
        if rep_kpi is not None:
            k = rep_kpi["kpi"]
            passage = dict(rep_kpi["passage"], score=1.0)
            _dbg(f"Raccourci KPI : {k['id']}")
            return _resultat(
                rep_kpi["answer"], "RAG", "ENTREPRISE",
                cited_sources=[(1, passage)], all_results=[passage],
                candidats_finaux=[passage], max_score=1.0,
                can_answer=True, confidence=1.0, extraits_verifier=[1],
                montant_structure={
                    "valeur": k["valeur"], "unite": k["unite"],
                    "scope": None if k["perimetre"] == "non_precise" else k["perimetre"],
                    "metric": k["indicateur"],
                },
                departement=departement_detecte,
                source_donnees="kpi_verifie",
            )

    if multi:
        result = process_comparative_question(
            query, model, index, metadata, user_role,
            selected_department=explicite,
        )
        result["departement"] = departement_detecte
        return result

    result = _pipeline_rag(
        query, model, index, metadata, user_role, departement,
        departement_contexte=departement_detecte,
    )

    if (
        departement and not explicite
        and result["mode"] in ("ABSENT", "GENERAL")
        and not result["all_results"]
    ):
        _dbg("Aucun resultat avec le filtre de departement : seconde passe sans filtre.")
        result = _pipeline_rag(
            query, model, index, metadata, user_role, None,
            departement_contexte=departement_detecte,
        )

    result["departement"] = departement_detecte
    return result
