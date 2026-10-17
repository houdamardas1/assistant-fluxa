"""
Service RAG : enveloppe fine autour de rag.pipeline.process_question_hybride.

Le role vient du jeton (jamais du corps de la requete). Le modele et l'index
sont charges une seule fois au demarrage.

LIMITE ACTUELLE : tenant_id est journalise mais le corpus est unique ; l'isolation
des donnees par tenant n'est pas encore appliquee (il faudra un champ
tenant_id sur chaque chunk et un filtre dans la recherche).
"""

from typing import Callable, Optional

_EVENEMENT_PAR_MODE = {
    "RAG": "ACCESS_GRANTED",
    "MULTI_INTENT": "ACCESS_GRANTED",
    "GENERAL": "ACCESS_GRANTED",
    "HORS_PERIMETRE": "ACCESS_DENIED",
    "ABSENT": "NO_ANSWER",
    "CLARIFICATION": "CLARIFICATION_REQUESTED",
}


def event_for_mode(mode: str) -> str:
    return _EVENEMENT_PAR_MODE.get(mode, "ACCESS_GRANTED")


def to_public(result: dict) -> dict:
    """Vue publique d'un resultat du pipeline : aucun contenu de chunk, aucun
    score interne, seulement la reponse et ses sources citees."""
    sources = [
        {
            "n": i,
            "fichier": r.get("fichier_source"),
            "page": r.get("page"),
            "entreprise": r.get("entreprise"),
            "type": r.get("type_document"),
            "demo": bool(r.get("is_synthetic", False)),
            "verifie": result.get("source_donnees") == "kpi_verifie",
        }
        for i, r in result.get("cited_sources", [])
    ]
    return {
        "answer": result["answer"],
        "mode": result["mode"],
        "departement": result.get("departement"),
        "confidence": round(float(result.get("confidence", 0.0)), 2),
        "sources": sources,
    }


class RagService:
    def __init__(self, index, metadata, model, pipeline: Optional[Callable] = None):
        self.index = index
        self.metadata = metadata
        self.model = model
        self._pipeline = pipeline

    @classmethod
    def from_disk(cls) -> "RagService":
        from sentence_transformers import SentenceTransformer

        from rag.config import MODEL_NAME
        from rag.retrieval import load_index

        index, metadata = load_index()
        return cls(index, metadata, SentenceTransformer(MODEL_NAME))

    @property
    def n_chunks(self) -> int:
        return len(self.metadata)

    def ask(self, question: str, role: str) -> dict:
        pipeline = self._pipeline
        if pipeline is None:
            from rag.pipeline import process_question_hybride as pipeline
        return pipeline(question, self.model, self.index, self.metadata, role)
