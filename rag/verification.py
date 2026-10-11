"""Verification de pertinence (LLM + repli local) et regles supplementaires du verificateur."""

import json
import re
from groq import RateLimitError

from .config import GROQ_VERIFY_MODEL, TOP_K_VERIFY, VERIFY_CHARS, _dbg
from .finance import (
    detect_famille,
    detect_metric,
    detect_scope,
    secteur_est_assurance,
)
from .juridique import detect_reference_article, est_titre_article
from .llm import QuotaError, groq_client
from .temporel import classify_chunk_temporal, detect_temporal_requirement
from .textutils import mots_utiles


def parse_json_response(content: str) -> dict:
    content = content.strip()

    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0].strip()

    start, end = content.find("{"), content.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("Aucun objet JSON trouve dans la reponse")

    return json.loads(content[start:end + 1])


def local_relevance_fallback(query: str, contexts: list) -> tuple:
    """Verification locale lorsque l'appel Groq echoue. Retourne
    (can_answer, confidence)."""
    if not contexts:
        return False, 0.0

    top_contexts = contexts[:TOP_K_VERIFY]
    annees_demandees = set(re.findall(r"\b(?:19|20)\d{2}\b", query))

    if annees_demandees:
        requested_year, temporal_mode = detect_temporal_requirement(query)

        if requested_year and temporal_mode == "actual":
            if not any(
                classify_chunk_temporal(c, requested_year) == "actual"
                for c in top_contexts
            ):
                _dbg(f"Fallback local : aucune preuve reelle pour {requested_year}.")
                return False, 0.0

        # L'annee est cherchee dans le contenu ET le nom du fichier.
        annees_docs = set()
        for ctx in top_contexts:
            texte = ctx.get("content", "") + " " + ctx.get("fichier_source", "")
            annees_docs.update(re.findall(r"\b(?:19|20)\d{2}\b", texte))

        if annees_demandees - annees_docs:
            _dbg("Fallback local : annee demandee absente des extraits.")
            return False, 0.0

    numero_article = detect_reference_article(query)

    if numero_article and not any(
        est_titre_article(c.get("content", ""), numero_article)
        for c in top_contexts
    ):
        _dbg(f"Fallback local : aucun extrait ne porte l'article {numero_article}.")
        return False, 0.0

    query_words = mots_utiles(query, longueur_min=4)

    if not query_words:
        return False, 0.0

    texte = " ".join(c.get("content", "").lower() for c in top_contexts)
    matches = sum(1 for w in query_words if re.search(rf"\b{re.escape(w)}\b", texte))
    match_ratio = matches / len(query_words)
    best_score = max(c.get("score", 0.0) for c in top_contexts)

    sources = [c.get("fichier_source") for c in top_contexts if c.get("fichier_source")]

    if not sources:
        return False, 0.0

    occurrences = sources.count(max(set(sources), key=sources.count))
    a_reglementaire = any(
        c.get("type_document") == "public_reglementaire" for c in top_contexts
    )

    if a_reglementaire and best_score >= 0.55 and occurrences >= 3 and match_ratio >= 0.35:
        return True, 0.75

    if best_score < 0.55 or occurrences < 3:
        return False, 0.0

    return (True, 0.70) if match_ratio >= 0.35 else (False, 0.0)


_REGLES_METRIC = {
    "chiffre_affaires": (
        "12. METRIQUE OBLIGATOIRE : la question demande le chiffre d'affaires. "
        "Un extrait qui contient uniquement des primes émises, primes acquises, "
        "revenus d'assurance ou produits des activités d'assurance ne constitue "
        "PAS une preuve du chiffre d'affaires, même si le périmètre, l'année et "
        "l'entreprise correspondent. Ne les transforme jamais en \"chiffre "
        "d'affaires\".\n"
    ),
    "primes_emises": (
        "12. METRIQUE OBLIGATOIRE : la question demande les primes émises. Un "
        "chiffre d'affaires, un résultat net ou des revenus d'assurance ne "
        "constituent PAS automatiquement une preuve des primes émises.\n"
    ),
    "revenus_assurance": (
        "12. METRIQUE OBLIGATOIRE : la question demande les revenus "
        "d'assurance. Les primes émises ou le chiffre d'affaires ne doivent "
        "pas être présentés comme tels sans preuve explicite.\n"
    ),
    "produits_activites_assurance": (
        "12. METRIQUE OBLIGATOIRE : la question demande les produits des "
        "activités d'assurance. Un chiffre d'affaires, des primes émises ou un "
        "résultat net ne doivent pas être présentés comme tels sans preuve "
        "explicite.\n"
    ),
    "resultat_net": (
        "12. METRIQUE OBLIGATOIRE : la question demande le résultat net. Un "
        "chiffre d'affaires, des primes émises ou des revenus d'assurance ne "
        "constituent PAS une preuve du résultat net.\n"
    ),
}


def _regles_verification(query: str, contexts: list) -> str:
    """Regles supplementaires du verificateur (article, secteur, perimetre,
    metrique, temporalite), en defense en profondeur des filtres Python."""
    regles = ""

    numero = detect_reference_article(query)

    if numero:
        regles += (
            f"8. La question porte sur l'article {numero}. Reponds true "
            "UNIQUEMENT si l'un des extraits contient le TEXTE de cet "
            "article. Une simple mention du type \"conformement a l'article "
            f"{numero}\" est un renvoi : dans ce cas, reponds false.\n"
        )

    if detect_famille(query) == "chiffre_affaires" and any(
        secteur_est_assurance(r.get("secteur")) for r in contexts[:TOP_K_VERIFY]
    ):
        regles += (
            "9. Si un extrait emploie LITTERALEMENT l'expression \"chiffre "
            "d'affaires\", il constitue la reponse prioritaire : reponds true "
            "et designe-le dans \"extraits\" de preference a tout autre.\n"
            "10. Ne considere PAS par defaut les primes émises/acquises, les "
            "produits des activités d'assurance ou les revenus d'assurance "
            "comme equivalents au chiffre d'affaires. N'accepte un indicateur "
            "sectoriel que si AUCUN extrait ne contient le terme litteral "
            "\"chiffre d'affaires\", et nomme-le alors comme tel.\n"
        )

    scope = detect_scope(query)

    if scope == "consolide":
        regles += (
            "11. PERIMETRE CONSOLIDE OBLIGATOIRE : un extrait \"résultats "
            "sociaux\" ou \"comptes sociaux\" ne peut PAS servir de preuve, "
            "même avec le même indicateur et la bonne année. Reponds false si "
            "aucun extrait ne fournit une valeur explicitement consolidée. Ne "
            "transforme jamais un chiffre social en chiffre consolidé.\n"
        )
    elif scope == "social":
        regles += (
            "11. PERIMETRE SOCIAL OBLIGATOIRE : un chiffre provenant "
            "uniquement de comptes consolidés ne peut pas servir de preuve. "
            "Reponds false si aucun extrait ne fournit le chiffre social "
            "demandé.\n"
        )

    regles += _REGLES_METRIC.get(detect_metric(query), "")

    year, mode = detect_temporal_requirement(query)

    if year and mode == "actual":
        regles += (
            f"13. TEMPORALITE OBLIGATOIRE : la question demande des "
            f"informations réalisées en {year}. Un passage disant seulement "
            f"qu'une action est prévue ou constitue un objectif pour {year} "
            "ne prouve PAS un résultat réalisé. Si seuls des éléments "
            "prospectifs sont fournis, reponds false.\n"
        )
    elif year and mode == "planned":
        regles += (
            f"13. TEMPORALITE : la question porte sur les plans/prévisions "
            f"pour {year}. Les passages prospectifs sont admissibles, mais ne "
            "les présente jamais comme des résultats déjà réalisés.\n"
        )

    return regles


def verify_relevance(query: str, contexts: list) -> tuple:
    """Retourne (can_answer, confidence, verify_error, extraits)."""
    if not contexts:
        return False, 0.0, False, []

    context_preview = "\n\n".join(
        f"[Extrait {i + 1} - {r['entreprise']} - page {r['page']}]\n"
        f"{r['content'][:VERIFY_CHARS]}"
        for i, r in enumerate(contexts[:TOP_K_VERIFY])
    )

    verification_prompt = (
        "Tu es un verificateur de pertinence pour un assistant RAG.\n\n"
        f"QUESTION UTILISATEUR :\n{query}\n\n"
        f"EXTRAITS DE DOCUMENTS :\n{context_preview}\n\n"
        "Determine si les extraits contiennent suffisamment d'informations "
        "factuelles pour repondre a la question.\n\n"
        "REGLES :\n"
        "1. Reponds true si les extraits permettent de construire une "
        "reponse factuelle a la question.\n"
        "2. Les informations peuvent etre reparties entre plusieurs "
        "extraits.\n"
        "3. Une reformulation ou un synonyme de la question est acceptable.\n"
        "4. Reponds false si les informations necessaires ne sont pas "
        "presentes.\n"
        "5. Reponds false si les seuls chiffres disponibles concernent une "
        "autre entite, un autre perimetre ou une autre devise que ce qui est "
        "demande.\n"
        "6. N'utilise aucune connaissance externe.\n"
        "7. Indique dans \"extraits\" les numeros des extraits qui portent "
        "reellement la reponse.\n"
        f"{_regles_verification(query, contexts)}"
        "\nReponds UNIQUEMENT avec un JSON valide, sans texte avant ou apres, "
        "sans backticks :\n"
        '{\n  "can_answer": true,\n  "confidence": 0.95,\n  "extraits": [1, 5]\n}'
    )

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_VERIFY_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un verificateur strict de pertinence RAG. "
                        "Reponds avec EXACTEMENT un objet JSON valide "
                        "contenant \"can_answer\" (boolean), \"confidence\" "
                        "(nombre entre 0 et 1) et \"extraits\" (liste "
                        "d'entiers). Exemple : {\"can_answer\": true, "
                        "\"confidence\": 0.95, \"extraits\": [1]}"
                    ),
                },
                {"role": "user", "content": verification_prompt},
            ],
            temperature=0.0,
            max_tokens=1200,
        )

        response_text = response.choices[0].message.content or ""
        _dbg(f"Verifier content : {response_text!r}")

        try:
            result = parse_json_response(response_text.strip())
        except Exception as parse_error:
            _dbg(f"Echec parsing du verifier : {parse_error}")
            can_answer, confidence = local_relevance_fallback(query, contexts)
            return can_answer, confidence, True, []

        can_answer = bool(result.get("can_answer", False))
        confidence = float(result.get("confidence", 0.0))
        extraits = result.get("extraits") or []

        valides = [
            n for n in extraits
            if isinstance(n, int) and 1 <= n <= len(contexts[:TOP_K_VERIFY])
        ]

        if can_answer and extraits and not valides:
            _dbg(f"Extraits cites invalides : {extraits}")
            confidence = min(confidence, 0.4)

        numero = detect_reference_article(query)

        if can_answer and numero:
            cibles = (
                [contexts[n - 1] for n in valides]
                if valides else contexts[:TOP_K_VERIFY]
            )
            if not any(est_titre_article(c.get("content", ""), numero) for c in cibles):
                _dbg(f"Aucun extrait ne porte le texte de l'article {numero}.")
                return False, 0.0, False, valides

        return can_answer, confidence, False, valides

    except RateLimitError as e:
        raise QuotaError(str(e)) from e

    except Exception as e:
        print(f"  [Debug] Erreur verification : {e}")
        can_answer, confidence = local_relevance_fallback(query, contexts)
        return can_answer, confidence, True, []
