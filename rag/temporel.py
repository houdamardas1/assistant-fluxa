"""Temporalite : annee demandee, chunk realise/prevu, incompatibilite temporelle."""

import re


TEMPORAL_PLANNED_PATTERNS = [
    r"\bpr[ée]vu(?:e|s|es)?\b", r"\bpr[ée]voit\b", r"\bpr[ée]vision(?:s)?\b",
    r"\bobjectif(?:s)?\b", r"\bpoursuivr(?:a|ont)\b",
    r"\bprendr(?:a|ont)\b", r"\bser(?:a|ont|aient)\b",
    r"\bdevr(?:a|ont|aient)\b",
    r"\benvisage(?:r|ant|ait|aient)?\b", r"\bplanifi(?:é|ée|és|ées|e|ent)\b",
    r"\b[àa] venir\b",
]


TEMPORAL_ACTUAL_PATTERNS = [
    r"\bau\s+31\s+(?:décembre|decembre)\s+{year}\b",
    r"\bexercice\s+{year}\b",
    r"\brésultats?\s+(?:annuels?\s+)?(?:de\s+)?{year}\b",
    r"\br[ée]sultats?\s+(?:sociaux|consolid[ée]s?)\b",
    r"\bs'établit\b", r"\bs'[ée]l[èe]ve\b", r"\bressort\s+[àa]\b",
    r"\ba\s+(?:augment|progress|diminu)[ée]\b",
    r"\ba\s+r[ée]alis[ée]\b",
]


def _report_year(chunk: dict) -> int | None:
    years = re.findall(r"\b20\d{2}\b", chunk.get("fichier_source", ""))
    return int(years[-1]) if years else None


def detect_temporal_requirement(query: str) -> tuple[int | None, str]:
    """(annee, mode) avec mode in {"any", "actual", "planned"}. Pour une
    annee passee, le mode par defaut est "actual" : un plan pour cette
    annee ne prouve pas un resultat realise."""
    years = re.findall(r"\b(?:19|20)\d{2}\b", query)
    year = int(years[0]) if years else None
    q = query.lower()

    if any(re.search(p, q, flags=re.IGNORECASE) for p in TEMPORAL_PLANNED_PATTERNS):
        return year, "planned"

    return year, "actual" if year else "any"


def classify_chunk_temporal(chunk: dict, requested_year: int | None) -> str:
    """"actual", "planned" ou "unknown" pour une annee donnee."""
    if requested_year is None:
        return "unknown"

    content = chunk.get("content", "")
    text = f"{content} {chunk.get('fichier_source', '')}"

    if not re.search(rf"\b{requested_year}\b", text):
        return "unknown"

    if any(re.search(p, content, flags=re.IGNORECASE)
           for p in TEMPORAL_PLANNED_PATTERNS):
        return "planned"

    actual = [p.format(year=requested_year) for p in TEMPORAL_ACTUAL_PATTERNS]

    if any(re.search(p, content, flags=re.IGNORECASE) for p in actual):
        return "actual"

    if _report_year(chunk) == requested_year:
        return "actual"

    return "unknown"


def temporal_incompatible(query: str, chunk: dict) -> bool:
    year, mode = detect_temporal_requirement(query)

    if year is None or mode == "any":
        return False

    status = classify_chunk_temporal(chunk, year)
    chunk["_temporal_status"] = status

    if mode == "actual":
        return status in {"planned", "unknown"}

    return status == "unknown"
