import logging, time
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.INFO)

from sentence_transformers import SentenceTransformer
from rag.config import MODEL_NAME
from rag.retrieval import load_index
from rag.llm import groq_client
from rag.pipeline import process_question_hybride

appels = []
_orig = groq_client.chat.completions.create

def _mesure(*a, **k):
    t0 = time.perf_counter()
    try:
        r = _orig(*a, **k)
        u = getattr(r, "usage", None)
        det = getattr(u, "completion_tokens_details", None)
        appels.append({
            "modele": k.get("model"), "s": round(time.perf_counter() - t0, 1),
            "prompt": getattr(u, "prompt_tokens", None), "sortie": getattr(u, "completion_tokens", None),
            "raisonnement": getattr(det, "reasoning_tokens", None),
            "effort": k.get("reasoning_effort", "(defaut)"), "max_tokens": k.get("max_tokens"),
        })
        return r
    except Exception as e:
        appels.append({"modele": k.get("model"), "s": round(time.perf_counter() - t0, 1), "erreur": type(e).__name__})
        raise

groq_client.chat.completions.create = _mesure

print("Chargement...")
model = SentenceTransformer(MODEL_NAME)
index, metadata = load_index()
questions = [
    ("rh", "Quelle est la duree de la periode d'essai ?"),
    ("it", "Quelles sont les exigences de sauvegarde selon la DNSSI ?"),
    ("direction", "Qui compose le conseil d'administration d'Unimer ?"),
]
for role, q in questions:
    appels.clear()
    t0 = time.perf_counter()
    r = process_question_hybride(q, model, index, metadata, role)
    total = time.perf_counter() - t0
    print("\n=== %s | role=%s | total %.1f s | mode=%s | %d appel(s) modele ===" % (q[:48], role, total, r["mode"], len(appels)))
    for i, a in enumerate(appels, 1):
        print("  appel %d : %s" % (i, a))
    print("  temps hors appels modele : %.1f s" % (total - sum(a["s"] for a in appels)))
