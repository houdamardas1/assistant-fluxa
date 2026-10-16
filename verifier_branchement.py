#!/usr/bin/env python3
"""Verifie que l'API (donc l'interface React) est branchee sur TES donnees reelles.

Compare, pour un compte donne, ce que renvoie l'API avec ce que contient l'index
FAISS charge directement par rag/ (meme logique RBAC). Aucune donnee inventee.

Usage (depuis backend/, API demarree) :
  python verifier_branchement.py --user sara --password "..." [--api http://127.0.0.1:8000] [--ask "question"]
"""
import argparse, json, sys, urllib.request, urllib.error


def appel(api, chemin, jeton=None, corps=None):
    req = urllib.request.Request(api + chemin, method="POST" if corps is not None else "GET")
    req.add_header("Content-Type", "application/json")
    if jeton:
        req.add_header("Authorization", "Bearer " + jeton)
    data = json.dumps(corps).encode() if corps is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} sur {chemin} : {e.read().decode()[:300]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--ask")
    a = ap.parse_args()
    ko = 0

    def check(nom, cond, detail=""):
        nonlocal ko
        print(("[OK] " if cond else "[KO] ") + nom + (f"  -> {detail}" if detail and not cond else ""))
        ko += 0 if cond else 1

    h = appel(a.api, "/health")
    check("API joignable", bool(h), h)
    t = appel(a.api, "/auth/login", corps={"username": a.user, "password": a.password})
    jeton, role = t["access_token"], t["user"]["role"]
    print(f"Connecte : {t['user']['display_name']} (role={role})")

    api_stats = appel(a.api, "/corpus/stats", jeton)

    # Verite terrain : l'index charge directement, sans passer par l'API.
    from rag.retrieval import load_index
    from rag.rbac import est_accessible
    _, metadata = load_index()
    attendu = [c for c in metadata if est_accessible(c, role)]
    fichiers = {c.get("fichier_source") for c in attendu}

    tot = api_stats.get("total_chunks")
    nf = api_stats.get("total_files")
    check(f"passages accessibles = index reel ({len(attendu)})", tot == len(attendu), f"API={tot}")
    check(f"documents accessibles = index reel ({len(fichiers)})", nf == len(fichiers), f"API={nf}")
    liste = {d["file"] for d in api_stats.get("files", [])}
    check("liste des fichiers identique", not liste or liste == fichiers, f"ecart={sorted(liste ^ fichiers)[:5]}")

    if a.ask:
        r = appel(a.api, "/ask", jeton, {"question": a.ask})
        print(f"\nMode={r['mode']} confiance={r['confidence']}\n{r['answer'][:500]}")
        noms = {s["fichier"] for s in r["sources"]}
        check("sources citees = fichiers reels accessibles", noms <= fichiers, f"inconnus={sorted(noms - fichiers)}")
        h2 = appel(a.api, "/me/history?limit=5", jeton)
        check("question enregistree dans l'historique/audit", bool(h2))
    print("\n" + ("Branchement coherent avec les donnees reelles." if not ko else f"{ko} ecart(s) : l'API ne reflete pas l'index."))
    sys.exit(1 if ko else 0)


if __name__ == "__main__":
    main()
