"""Generation des reponses (RAG et generale) et gestion des citations [Source N]."""

import re

from .config import LIBELLE_DEPARTEMENT, _dbg
from .llm import _chat
from .messages import MESSAGE_ABSENTE
from .textutils import nettoyer_reponse


RE_BLOC_CROCHETS = re.compile(r"[\[【]([^\]】]{0,200})[\]】]")


RE_NUMEROS_SOURCE = re.compile(
    r"sources?\s*n?[°o]?\s*(\d+(?:\s*(?:,|;|et|&|/)\s*\d+)*)",
    flags=re.IGNORECASE,
)


def extract_cited_sources(answer: str, results: list) -> list:
    """Sources explicitement citees ("[Source 1 - fichier, page 125]",
    "[Sources 2 et 3]"...)."""
    cited = set()

    for bloc in RE_BLOC_CROCHETS.findall(answer):
        for m in RE_NUMEROS_SOURCE.finditer(bloc):
            cited.update(int(n) for n in re.findall(r"\d+", m.group(1)))

    return [(i, r) for i, r in enumerate(results, start=1) if i in cited]


def _remap_source_numbers(text: str, mapping: dict) -> str:
    """Reecrit les numeros LOCAUX des blocs [Source N] en numeros GLOBAUX."""

    def _bloc(m):
        bloc = m.group(0)
        nouveau = re.sub(
            r"\d+", lambda nm: str(mapping.get(int(nm.group(0)), nm.group(0))),
            m.group(1),
        )
        return bloc[0] + nouveau + bloc[-1]

    return RE_BLOC_CROCHETS.sub(_bloc, text)


def renumber_multi_intent_sources(sous_reponses: list) -> list:
    """Numerotation globale unique des sources citees par plusieurs
    sous-reponses ; met a jour le texte de chaque sous-reponse."""
    combined, compteur = [], 1

    for sr in sous_reponses:
        res = sr["result"]
        local_cited = res.get("cited_sources", [])

        if not local_cited:
            continue

        mapping = {}

        for local_i, r in local_cited:
            mapping[local_i] = compteur
            combined.append((compteur, r))
            compteur += 1

        res["answer"] = _remap_source_numbers(res.get("answer", ""), mapping)

    return combined


def _contexte_departement(departement: str | None) -> str:
    if departement not in LIBELLE_DEPARTEMENT:
        return ""
    return (
        f"La question relève du département {LIBELLE_DEPARTEMENT[departement]} : "
        "adapte le vocabulaire et mets en avant les éléments les plus utiles "
        "à ce métier.\n"
    )


_FORMAT_TEXTE_PROPRE = (
    "FORMAT OBLIGATOIRE : texte brut professionnel. N'utilise AUCUN markdown : "
    "pas de '#', pas de '**', pas de '__', pas de tableau, pas de balise HTML. "
    "Un titre est une ligne simple terminée par ':' ; une liste utilise des "
    "lignes commençant par '- '. Phrases courtes et claires.\n"
)


def _nom_source(r: dict) -> str:
    """Nom lisible d'une source : entreprise, ou "Texte reglementaire"."""
    if r.get("entreprise"):
        return str(r["entreprise"])
    if r.get("type_document") == "public_reglementaire":
        return "Texte réglementaire"
    return "Document interne"


def generate_general_answer(query: str, departement: str | None = None) -> str:
    """Reponse generale (sans RAG), en texte propre."""
    system_prompt = (
        "Tu es un assistant professionnel au sein d'une entreprise.\n"
        "La question est d'ordre général et ne concerne PAS les données "
        "internes de l'entreprise : réponds avec tes connaissances générales, "
        "de façon précise, concise et professionnelle, en français.\n"
        "N'invente jamais de données propres à une entreprise.\n"
        "Le contexte est le Maroc : ne cite jamais le droit ou la "
        "réglementation d'un autre pays sauf si la question le demande.\n"
        f"{_contexte_departement(departement)}"
        f"{_FORMAT_TEXTE_PROPRE}"
    )

    response = _chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.2,
        max_tokens=1500,
    )

    choix = response.choices[0]
    _dbg(f"Reponse generale : finish_reason={choix.finish_reason}")
    texte = nettoyer_reponse(choix.message.content)

    return texte or (
        "Je n'ai pas pu formuler de réponse à cette question. "
        "Pouvez-vous la reformuler ?"
    )


def generate_answer(
    query: str,
    rag_results: list,
    user_role: str,
    departement: str | None = None,
) -> str:
    """Reponse ENTREPRISE (RAG) a partir des extraits DEJA valides par
    verify_relevance(), avec citations [Source N], en texte propre."""
    if not rag_results:
        return MESSAGE_ABSENTE

    contexte = "\n\n".join(
        f"[Source {i}] {_nom_source(r)} - {r.get('fichier_source')} - "
        f"page {r.get('page')}"
        + (
            " (DONNEE DE DEMONSTRATION SYNTHETIQUE -- a signaler comme telle)"
            if r.get("is_synthetic") else ""
        )
        + f"\n{r.get('content', '')[:1500]}"
        for i, r in enumerate(rag_results, start=1)
    )

    system_prompt = (
        "Tu es un assistant d'entreprise qui répond STRICTEMENT à partir des "
        "extraits de documents fournis ci-dessous. Tu n'utilises AUCUNE "
        "connaissance externe et n'inventes JAMAIS de chiffre, de nom ou de "
        "fait absent des extraits.\n\n"
        "REGLES OBLIGATOIRES :\n"
        "1. Chaque affirmation factuelle est suivie d'une citation au format "
        "[Source N], N étant le numéro de l'extrait ci-dessous "
        "(ex: [Source 1]). Plusieurs sources : [Source 1, Source 2].\n"
        "2. N'utilise QUE des crochets ASCII [ ] pour les citations, jamais "
        "de crochets pleine largeur.\n"
        "3. Si un extrait est marqué DONNEE DE DEMONSTRATION SYNTHETIQUE, "
        "signale-le et ne le présente jamais comme une donnée officielle.\n"
        "4. Si les extraits emploient un indicateur sectoriel équivalent "
        "(ex: primes émises pour une compagnie d'assurance), explique cette "
        "équivalence clairement plutôt que de la passer sous silence.\n"
        "5. Si une partie de la question n'est pas couverte par les extraits, "
        "dis-le explicitement au lieu de deviner.\n"
        "6. Réponds en français, de façon concise et factuelle.\n"
        "7. Pour tout chiffre cité, indique le périmètre (social ou "
        "consolidé) et l'année lorsque l'extrait les précise.\n"
        f"{_contexte_departement(departement)}"
        f"{_FORMAT_TEXTE_PROPRE}\n"
        f"Rôle de l'utilisateur : {user_role}\n\n"
        "EXTRAITS DE DOCUMENTS (déjà vérifiés comme pertinents) :\n"
        f"{contexte}"
    )

    response = _chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.0,
        max_tokens=3000,
    )

    choix = response.choices[0]
    _dbg(f"Reponse RAG : finish_reason={choix.finish_reason}")
    texte = nettoyer_reponse(choix.message.content)

    return texte or MESSAGE_ABSENTE
