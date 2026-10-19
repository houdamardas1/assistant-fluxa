"""Test de fumee de l'API comme le fait l'interface : connexion, puis /ask par cas."""
import argparse
import getpass
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

MODES = {"RAG", "MULTI_INTENT", "GENERAL", "ABSENT", "HORS_PERIMETRE", "CLARIFICATION"}
LLM = {"RAG", "MULTI_INTENT", "GENERAL"}


def charger(chemin):
    d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    return d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))


def attendus(cas):
    m = cas.get("expected_mode")
    return set(m) if isinstance(m, list) else ({m} if m else set())


def poser(client, token, question):
    for essai in range(2):
        t0 = time.time()
        r = client.post("/ask", json={"question": question},
                        headers={"Authorization": f"Bearer {token}"})
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 429 and essai == 0:
            print("    429 : attente 65 s puis nouvel essai")
            time.sleep(65)
            continue
        return r, ms
    return r, ms


def verifier(r, attendu):
    if r.status_code != 200:
        return "ERREUR", [f"HTTP {r.status_code} : {r.text[:150]}"], None
    try:
        j = r.json()
    except ValueError:
        return "ERREUR", ["JSON invalide"], None
    pb = [f"champ manquant : {k}" for k in
          ("request_id", "answer", "mode", "confidence", "sources") if k not in j]
    if pb:
        return "ERREUR", pb, j
    if not str(j["answer"]).strip():
        pb.append("reponse vide")
    if j["mode"] not in MODES:
        pb.append(f"mode inconnu : {j['mode']}")
    if not isinstance(j["confidence"], (int, float)) or not 0 <= j["confidence"] <= 1:
        pb.append(f"confiance invalide : {j['confidence']}")
    if j["mode"] == "RAG" and not j["sources"]:
        pb.append("RAG sans source")
    if any(s in str(j["answer"]) for s in ("Traceback", "Internal Server Error")):
        pb.append("trace d'erreur dans la reponse")
    if pb:
        return "ERREUR", pb, j
    if attendu and j["mode"] not in attendu:
        return "ECART", [f"attendu {sorted(attendu)}, obtenu {j['mode']}"], j
    return "OK", [], j


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--cas", default="data/eval/v1.json")
    ap.add_argument("--prefixe", default="demo_")
    ap.add_argument("--modes", default="", help="filtre sur le mode attendu, ex. HORS_PERIMETRE,ABSENT")
    ap.add_argument("--ids", default="")
    ap.add_argument("--debut", type=int, default=0, help="saute les N premiers cas filtres")
    ap.add_argument("--limite-llm", type=int, default=0, help="stoppe apres N reponses utilisant le LLM")
    ap.add_argument("--pause", type=int, default=45, help="secondes apres une reponse LLM")
    a = ap.parse_args()

    cas = charger(a.cas)
    if a.modes:
        voulus = set(a.modes.split(","))
        cas = [c for c in cas if attendus(c) & voulus]
    if a.ids:
        ids = set(a.ids.split(","))
        cas = [c for c in cas if c["id"] in ids]
    cas = cas[a.debut:]
    print(f"{len(cas)} cas a passer sur {a.url}")

    client = httpx.Client(base_url=a.url, timeout=120)
    jetons = {}
    resultats = []
    nb_llm = 0
    for i, c in enumerate(cas, 1):
        role = c["role"]
        if role not in jetons:
            user = f"{a.prefixe}{role}"
            mdp = getpass.getpass(f"Mot de passe de {user} : ")
            r = client.post("/auth/login", json={"username": user, "password": mdp})
            jetons[role] = r.json()["access_token"] if r.status_code == 200 else None
            if jetons[role] is None:
                print(f"  connexion refusee pour {user} (HTTP {r.status_code})")
        if jetons[role] is None:
            verdict, details, j, ms = "ERREUR", ["connexion impossible"], None, 0
        else:
            r, ms = poser(client, jetons[role], c["question"])
            verdict, details, j = verifier(r, attendus(c))
        mode = j["mode"] if j else "-"
        print(f"[{i:02d}/{len(cas)}] {verdict:6} {c['id'][:38]:38} {role:9} "
              f"{mode:15} {ms:5} ms  {' ; '.join(details)}")
        resultats.append({"id": c["id"], "role": role, "verdict": verdict,
                          "mode_obtenu": mode, "ms": ms, "details": details})
        if j and j["mode"] in LLM:
            nb_llm += 1
            if a.limite_llm and nb_llm >= a.limite_llm:
                print(f"limite de {a.limite_llm} reponses LLM atteinte : arret")
                break
            if i < len(cas):
                time.sleep(a.pause)

    comptes = {v: sum(1 for x in resultats if x["verdict"] == v) for v in ("OK", "ECART", "ERREUR")}
    print(f"\nBilan : {comptes} sur {len(resultats)} cas, {nb_llm} reponses LLM")
    sortie = Path("data/eval") / f"smoke_ui_{datetime.now():%Y%m%d_%H%M%S}.json"
    sortie.write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Rapport :", sortie)
    sys.exit(1 if comptes["ERREUR"] else 0)


main()
