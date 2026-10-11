"""Test d'equivalence de comportement : monolithe vs package rag (hors ligne).

Usage (depuis backend/, avec assistant_legacy.py + assistant.py facade + rag/) :
    python e2e_equivalence.py
Aucun appel Groq, aucun index reel : faux embeddings, faux FAISS, faux Groq
deterministes. Compare, sur 29 questions couvrant les 6 modes de sortie, les
resultats complets du pipeline, l'affichage, ~2 700 appels de fonctions pures,
evaluer_cas et main(--question).
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import types
import unicodedata
import zlib
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- stubs ----
DIM = 128


def _tokens(text):
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", t)


class FakeModel:
    def __init__(self, *a, **k):
        pass

    def encode(self, textes, convert_to_numpy=True):
        out = np.zeros((len(textes), DIM), dtype="float64")
        for i, t in enumerate(textes):
            for w in _tokens(t):
                out[i, zlib.crc32(w.encode()) % DIM] += 1.0
        return out


class FakeIndex:
    def __init__(self, matrice):
        self.m = matrice.astype("float32")
        self.ntotal = len(self.m)

    def search(self, q, k):
        sims = self.m @ q[0]
        ordre = np.argsort(-sims, kind="stable")[:k]
        return np.array([sims[ordre]]), np.array([ordre])


faiss_stub = types.ModuleType("faiss")


def _normalize(x):
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    x /= n


faiss_stub.normalize_L2 = _normalize
faiss_stub.read_index = lambda p: INDEX_GLOBAL

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *a, **k: None


class RateLimitError(Exception):
    pass


class _Msg:
    def __init__(self, c):
        self.content = c


class _Choice:
    def __init__(self, c):
        self.message = _Msg(c)
        self.finish_reason = "stop"


class _Resp:
    def __init__(self, c):
        self.choices = [_Choice(c)]


class _Completions:
    def create(self, model=None, messages=None, **kw):
        sys_c = messages[0]["content"]
        user_c = messages[-1]["content"]
        if "verificateur strict" in sys_c:
            ok = "1999" not in user_c and "Apple" not in user_c
            return _Resp(json.dumps(
                {"can_answer": ok, "confidence": 0.9, "extraits": [1] if ok else []}
            ))
        if "REGLES OBLIGATOIRES" in sys_c:
            return _Resp("**Reponse** fondee sur les extraits [Source 1, Source 2].")
        return _Resp("## Reponse generale\n* point un")


class _Chat:
    completions = _Completions()


class Groq:
    def __init__(self, *a, **k):
        self.chat = _Chat()


groq_stub = types.ModuleType("groq")
groq_stub.Groq = Groq
groq_stub.RateLimitError = RateLimitError

st_stub = types.ModuleType("sentence_transformers")
st_stub.SentenceTransformer = FakeModel

for name, mod in (("faiss", faiss_stub), ("dotenv", dotenv_stub),
                  ("groq", groq_stub), ("sentence_transformers", st_stub)):
    sys.modules[name] = mod

os.environ["GROQ_API_KEY"] = "test"

# ----------------------------------------------------------- corpus --------


def chunk(f, p, ent, dept, typ, txt, sect=None):
    return {
        "fichier_source": f, "page": p, "entreprise": ent, "secteur": sect,
        "departement": dept, "type_document": typ, "content": txt,
        "is_synthetic": False,
    }


W, U, D = "Wafa_Assurance_RFA_2025.pdf", "UNIMER_RFA_2024.pdf", "DNSSI_Directive_Securite_SI.pdf"
CT, CO, L31, CC = ("Code_du_Travail_Loi_65-99.pdf", "Code_Obligations_Contrats_DOC.pdf",
                   "Loi_31-08_Protection_Consommateur.pdf", "Code_de_Commerce_Loi_15-95.pdf")
CDG = "CDG_Capital_RFA_2024.pdf"

METADATA = [
    chunk(W, 64, "Wafa_Assurance", "finance", "entreprise",
          "Resultats sociaux 2025. Le chiffre d'affaires social de Wafa Assurance s'etablit a 12 738 MDH en 2025.", "Assurance"),
    chunk(W, 65, "Wafa_Assurance", "finance", "entreprise",
          "Activite consolidee 2025 : les primes emises consolidees atteignent 15 226 MDH. Resultats consolides.", "Assurance"),
    chunk(W, 66, "Wafa_Assurance", "finance", "entreprise",
          "Resultats consolides 2025. Le resultat net consolide s'eleve a 1 800 MDH en 2025.", "Assurance"),
    chunk(W, 67, "Wafa_Assurance", "finance", "entreprise",
          "Resultats sociaux 2025. Le resultat net social s'eleve a 1 500 MDH en 2025.", "Assurance"),
    chunk(W, 22, "Wafa_Assurance", "finance", "entreprise",
          "Chiffre d'affaires de la filiale Cote d'Ivoire 2025 : 900 MFCFA.", "Assurance"),
    chunk(U, 19, "Unimer", "direction", "entreprise",
          "Conseil d'administration d'Unimer : President HASSAR, administrateurs DELIMAR et RETAIL HOLDING."),
    chunk(U, 20, "Unimer", "direction", "entreprise",
          "Gouvernance : le conseil de surveillance et le comite d'audit se reunissent chaque trimestre."),
    chunk(CDG, 12, "CDG_Capital", "finance", "entreprise",
          "Resultat net consolide 2024 de CDG Capital : 350 MDH. Comptes consolides."),
    chunk(D, 22, None, "it", "public_reglementaire",
          "Sauvegarde Objectif 18 : se proteger contre la perte de donnees. EXP-SAUV-PROC : procedures de sauvegarde."),
    chunk(D, 30, None, "it", "public_reglementaire",
          "Mots de passe : la politique de securite impose des mots de passe robustes et renouveles."),
    chunk(CT, 10, None, "rh", "public_reglementaire",
          "Conges annuels payes : le salarie a droit a un conge annuel de jours ouvrables par mois de service."),
    chunk(CT, 11, None, "rh", "public_reglementaire",
          "Periode d'essai : la duree de la periode d'essai est fixee par le contrat de travail."),
    chunk(CO, 1, None, "juridique", "public_reglementaire",
          "Code des obligations et des contrats. Article 461 : interpretation des conventions."),
    chunk(L31, 4, None, "commerce", "public_reglementaire",
          "Protection du consommateur. Article 15 : clauses abusives et desequilibre significatif entre les parties."),
    chunk(CC, 97, None, "commerce", "public_reglementaire",
          "Code de commerce. Article 5 : registre du commerce et immatriculation, tarifs et commandes."),
    chunk("Auto_Nejma_RFA_2023.pdf", 5, "Auto_Nejma", "marketing", "entreprise",
          "Chiffre d'affaires d'Auto Nejma en 2023 : reseau de succursales et concessionnaires."),
]

_model = FakeModel()
_mat = _model.encode([c["content"] for c in METADATA]).astype("float32")
_normalize(_mat)
INDEX_GLOBAL = FakeIndex(_mat)

# -------------------------------------------------------- chargement -------
# Par defaut : dossier courant (backend/) contenant assistant.py (facade),
# rag/ et assistant_legacy.py (l'ancien monolithe).
sys.path.insert(0, os.environ.get("NEW_ROOT", "."))   # package rag + facade assistant
sys.path.insert(0, os.environ.get("OLD_ROOT", "."))   # assistant_legacy
import assistant as NEW            # noqa: E402
import assistant_legacy as OLD     # noqa: E402

assert NEW.__file__ != OLD.__file__


def resume(r):
    return {
        "answer": r["answer"], "mode": r["mode"], "type": r["type"],
        "dept": r.get("departement"), "can": r["can_answer"],
        "conf": r["confidence"], "verr": r["verify_error"],
        "extraits": r["extraits_verifier"], "montant": r["montant_structure"],
        "incoh": r["incoherence_citation"], "max": round(r["max_score"], 6),
        "finaux": [(x["fichier_source"], x["page"]) for x in r["candidats_finaux"]],
        "cited": [(i, x["fichier_source"], x["page"]) for i, x in r["cited_sources"]],
        "all": [(x["fichier_source"], x["page"], round(x["score"], 6)) for x in r["all_results"]],
        "sous": [resume(s["result"]) for s in r.get("sous_reponses", [])],
    }


QUESTIONS = [
    ("finance", "Quel est le chiffre d'affaires de Wafa Assurance en 2025 ?"),
    ("finance", "Quel est le chiffre d'affaires social de Wafa Assurance en 2025 ?"),
    ("finance", "Quelles sont les primes emises consolidees de Wafa Assurance en 2025 ?"),
    ("finance", "Quel est le resultat net de Wafa Assurance en 2025 ?"),
    ("finance", "Quel est le resultat net consolide de Wafa Assurance en 2025 ?"),
    ("finance", "Quel est le resultat net de Wafa Assurance en 1999 ?"),
    ("finance", "Quel est le chiffre d'affaires de Wafa Assurance en 2030 ?"),
    ("finance", "Compare le chiffre d'affaires social et les primes emises consolidees de Wafa Assurance en 2025"),
    ("finance", "Quel est le resultat net consolide de CDG Capital ?"),
    ("finance", "Quel est le chiffre d'affaires d'Apple en 2025 ?"),
    ("finance", "Quel est le chiffre d'affaires d'Auto Nejma ?"),
    ("finance", "Quels sont les tarifs ?"),
    ("finance", "Qu'est-ce que l'inflation ?"),
    ("direction", "Qui compose le conseil d'administration d'Unimer ?"),
    ("direction", "Quelle est la gouvernance d'Unimer ?"),
    ("it", "Quelles sont les exigences de sauvegarde selon la DNSSI ?"),
    ("it", "Que dit la DNSSI sur la securite des mots de passe ?"),
    ("it", "Qui compose le conseil d'administration d'Unimer ?"),
    ("rh", "Combien de jours de conges annuels ?"),
    ("rh", "Quelle est la duree de la periode d'essai ?"),
    ("rh", "Quel est le chiffre d'affaires de Wafa Assurance en 2025 ?"),
    ("rh", "Que dit le Code des obligations sur les clauses abusives ?"),
    ("juridique", "Que dit le Code des obligations sur les clauses abusives ?"),
    ("juridique", "Que dit l'article 15 sur les clauses abusives ?"),
    ("juridique", "Que dit l'article 999 du code ?"),
    ("tous", "Quel est le chiffre d'affaires de Wafa Assurance en 2025 ?"),
    ("tous", "Quelle est la capitale du Maroc ?"),
    ("marketing", "Quel est le resultat net de Wafa Assurance en 2025 ?"),
    ("commerce", "Quels sont les tarifs ?"),
]

echecs = 0


def cmp(nom, a, b):
    global echecs
    if a == b:
        return True
    echecs += 1
    print(f"  DIFFERENCE sur {nom}")
    if isinstance(a, dict):
        for k in a:
            if a[k] != b.get(k):
                print(f"    {k}: OLD={a[k]!r:.200}  NEW={b.get(k)!r:.200}")
    else:
        print(f"    OLD={a!r:.300}\n    NEW={b!r:.300}")
    return False


# 1. Pipeline complet
ok_q = 0
modes = {}
for role, q in QUESTIONS:
    ro = OLD.process_question_hybride(q, _model, INDEX_GLOBAL, METADATA, role)
    rn = NEW.process_question_hybride(q, _model, INDEX_GLOBAL, METADATA, role)
    modes[ro["mode"]] = modes.get(ro["mode"], 0) + 1
    if cmp(f"pipeline [{role}] {q}", resume(ro), resume(rn)):
        ok_q += 1
    # affichage
    bo, bn = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(bo):
        OLD._afficher_resultat(ro)
    with contextlib.redirect_stdout(bn):
        NEW._afficher_resultat(rn)
    cmp(f"affichage [{role}] {q}", bo.getvalue(), bn.getvalue())

print(f"Pipeline : {ok_q}/{len(QUESTIONS)} questions identiques ; modes couverts : {modes}")

# 2. Fonctions pures sur un echantillon
ECH = [q for _, q in QUESTIONS] + ["Que dit l'article 12 ?", "primes brutes emises groupe 2024",
                                    "resultat sociaux consolides 2023 prevu"]
pures = ["detect_famille", "detect_scope", "detect_metric", "detect_intents",
         "detect_reference_article", "detect_temporal_requirement", "detect_intent",
         "mots_utiles", "_norm", "nettoyer_reponse"]
n_pures = 0
for f in pures:
    for q in ECH:
        n_pures += 1
        cmp(f"{f}({q!r})", getattr(OLD, f)(q), getattr(NEW, f)(q))
for q in ECH:
    for c in METADATA:
        n_pures += 3
        cmp("scope_incompatible", OLD.scope_incompatible(q, c["content"]), NEW.scope_incompatible(q, c["content"]))
        cmp("metric_incompatible", OLD.metric_incompatible(q, c["content"]), NEW.metric_incompatible(q, c["content"]))
        cmp("detect_chunk_scope", OLD.detect_chunk_scope(c["content"]), NEW.detect_chunk_scope(c["content"]))
for c in METADATA:
    for r in NEW.ROLES_DISPONIBLES:
        n_pures += 2
        cmp("effective_allowed_roles", OLD.effective_allowed_roles(c), NEW.effective_allowed_roles(c))
        cmp("est_accessible", OLD.est_accessible(c, r), NEW.est_accessible(c, r))
for r in NEW.ROLES_DISPONIBLES:
    for d in list(NEW.DEPARTEMENTS) + [None]:
        n_pures += 2
        cmp("department_access_denied", OLD.department_access_denied(r, d), NEW.department_access_denied(r, d))
        cmp("message_refus_acces", OLD.message_refus_acces(r, d), NEW.message_refus_acces(r, d))
for q in ECH:
    for r in NEW.ROLES_DISPONIBLES:
        n_pures += 1
        cmp("detect_department", OLD.detect_department(q, r), NEW.detect_department(q, r))
        n_pures += 1
        cmp("detect_department_embeddings", OLD.detect_department_embeddings(q, _model, r),
            NEW.detect_department_embeddings(q, _model, r))
txts = ["Voir [Source 1, Source 2] et [Sources 2 et 3] puis 【Source 4】", "rien"]
for t in txts:
    n_pures += 1
    cmp("extract_cited_sources", [i for i, _ in OLD.extract_cited_sources(t, METADATA)],
        [i for i, _ in NEW.extract_cited_sources(t, METADATA)])
for t in ["12 738 MDH", "1.234,5 MAD", "abc", "5 MEUR"]:
    n_pures += 1
    cmp("extraire_montant", OLD.extraire_montant(t), NEW.extraire_montant(t))
print(f"Fonctions pures : {n_pures} comparaisons")

# 3. Evaluation
cas = [
    {"id": "a", "role": "finance", "question": QUESTIONS[0][1], "expected_mode": "RAG",
     "expected_source": W, "expected_contains": ["12 738"]},
    {"id": "b", "role": "finance", "question": QUESTIONS[3][1], "expected_mode": ["RAG", "CLARIFICATION"],
     "expected_source": W},
    {"id": "c", "role": "rh", "question": QUESTIONS[20][1], "expected_mode": "HORS_PERIMETRE",
     "expected_not_contains": ["12 738"]},
    {"id": "d", "role": "tous", "question": QUESTIONS[26][1], "expected_mode": "GENERAL"},
]
res_o, res_n = [], []
for c in cas:
    a = OLD.evaluer_cas(c, _model, INDEX_GLOBAL, METADATA)
    b = NEW.evaluer_cas(c, _model, INDEX_GLOBAL, METADATA)
    a["latence_s"] = b["latence_s"] = 0
    cmp(f"evaluer_cas {c['id']}", a, b)
    res_o.append(a)
    res_n.append(b)
cmp("resumer_evaluation", {k: v for k, v in OLD.resumer_evaluation(res_o).items() if "latence" not in k},
    {k: v for k, v in NEW.resumer_evaluation(res_n).items() if "latence" not in k})
cmp("snapshot_configuration", OLD._snapshot_configuration(), NEW._snapshot_configuration())

# 4. main(--question) de bout en bout, avec un vrai dossier data/index
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "data", "index"))
with open(os.path.join(tmp, "data", "index", "metadata.json"), "w", encoding="utf-8") as f:
    json.dump(METADATA, f)
cwd = os.getcwd()
os.chdir(tmp)
sorties = {}
for tag, mod in (("OLD", OLD), ("NEW", NEW)):
    for args in (["--role", "finance", "--question", QUESTIONS[0][1]],
                 ["--role", "it", "--question", QUESTIONS[15][1]],
                 ["--role", "rh", "--question", QUESTIONS[20][1]]):
        buf = io.StringIO()
        sys.argv = ["assistant.py"] + args
        with contextlib.redirect_stdout(buf):
            mod.main()
        sorties.setdefault(tuple(args), {})[tag] = buf.getvalue()
os.chdir(cwd)
for args, d in sorties.items():
    cmp(f"main {args}", d["OLD"], d["NEW"])
print(f"main() : {len(sorties)} executions CLI comparees")

print("\nRESULTAT E2E :", "EQUIVALENT" if echecs == 0 else f"{echecs} DIFFERENCE(S)")
sys.exit(0 if echecs == 0 else 1)
