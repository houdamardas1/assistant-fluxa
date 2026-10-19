"""Import des jeux de donnees dans PostgreSQL (schema `corpus`).

Usage (depuis backend/) :  python scripts/import_datasets_pg.py

La base est une COPIE re-importable des fichiers (metadata.json, kpi, eval,
inventaire des PDF). L'API continue de lire FAISS + metadata.json.
Connexion : POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB du fichier .env,
sur 127.0.0.1:15432 (PG_HOST / PG_PORT pour changer). Rien n'est affiche
du mot de passe.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    import psycopg
except ImportError:
    try:
        import psycopg2 as psycopg
    except ImportError:
        sys.exit('Pilote PostgreSQL absent : pip install "psycopg[binary]"')


def charger_env():
    env = dict(os.environ)
    f = ROOT / ".env"
    if f.exists():
        for ligne in f.read_text(encoding="utf-8-sig").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            k, v = ligne.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


SCHEMA = """
CREATE SCHEMA IF NOT EXISTS corpus;
CREATE TABLE IF NOT EXISTS corpus.documents (
  fichier_source text PRIMARY KEY, entreprise text, secteur text,
  type_document text, is_synthetic boolean, nb_passages integer,
  nb_pages integer, chemin_raw text, taille_octets bigint, sha256 text,
  importe_le timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS corpus.passages (
  faiss_id integer PRIMARY KEY,
  fichier_source text REFERENCES corpus.documents(fichier_source),
  page integer, content text, entreprise text, secteur text,
  type_document text, is_synthetic boolean, departement text,
  departements text[], allowed_roles text[], access_roles text[],
  extra jsonb);
CREATE TABLE IF NOT EXISTS corpus.kpi (
  id text PRIMARY KEY, entreprise text, indicateur text, libelle text,
  annee integer, valeur double precision, unite text, record jsonb);
CREATE TABLE IF NOT EXISTS corpus.eval_cases (
  id text PRIMARY KEY, role text, statut text, question text,
  expected_mode jsonb, expected_source text, expected_contains jsonb,
  expected_departement text, record jsonb);
"""

CONNUS = {"content", "page", "entreprise", "secteur", "fichier_source",
          "allowed_roles", "is_synthetic", "type_document", "departement",
          "access_roles", "departements"}


def propre(x):
    return x.replace("\x00", "") if isinstance(x, str) else x


def jdump(x):
    return json.dumps(x, ensure_ascii=False)


def flottant(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def entier(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def main():
    env = charger_env()
    for cle in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        if not env.get(cle):
            sys.exit("Variable manquante dans .env : " + cle)

    metadata = json.loads((ROOT / "data/index/metadata.json").read_text(encoding="utf-8"))
    kpi = json.loads((ROOT / "data/kpi/kpi_v1.json").read_text(encoding="utf-8"))["kpi"]
    cas = json.loads((ROOT / "data/eval/v1.json").read_text(encoding="utf-8"))["cas"]

    # inventaire des PDF sources (par nom de fichier)
    raw = {}
    for dossier, _, fichiers in os.walk(ROOT / "data/raw"):
        for nom in fichiers:
            if nom.lower().endswith(".pdf"):
                raw[nom] = Path(dossier) / nom

    # documents = regroupement des passages par fichier source
    docs = {}
    for m in metadata:
        f = m.get("fichier_source")
        if not f:
            continue
        d = docs.setdefault(f, {"entreprise": m.get("entreprise"), "secteur": m.get("secteur"),
                                "type_document": m.get("type_document"),
                                "is_synthetic": m.get("is_synthetic"), "n": 0, "pages": 0})
        d["n"] += 1
        d["pages"] = max(d["pages"], entier(m.get("page")) or 0)

    try:
        conn = psycopg.connect(
            host=env.get("PG_HOST", "127.0.0.1"), port=int(env.get("PG_PORT", "15432")),
            user=env["POSTGRES_USER"], password=env["POSTGRES_PASSWORD"],
            dbname=env["POSTGRES_DB"])
    except Exception as e:
        sys.exit("Connexion PostgreSQL impossible (%s). Le conteneur postgres est-il demarre ?"
                 % type(e).__name__)

    cur = conn.cursor()
    cur.execute(SCHEMA)
    cur.execute("TRUNCATE corpus.passages, corpus.documents, corpus.kpi, corpus.eval_cases")

    for f, d in docs.items():
        chemin, taille, sha = None, None, None
        if f in raw:
            p = raw[f]
            chemin = str(p.relative_to(ROOT)).replace("\\", "/")
            taille = p.stat().st_size
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
        cur.execute(
            "INSERT INTO corpus.documents (fichier_source, entreprise, secteur, type_document,"
            " is_synthetic, nb_passages, nb_pages, chemin_raw, taille_octets, sha256)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (f, d["entreprise"], d["secteur"], d["type_document"], d["is_synthetic"],
             d["n"], d["pages"], chemin, taille, sha))

    for i, m in enumerate(metadata):
        extra = {k: v for k, v in m.items() if k not in CONNUS}
        cur.execute(
            "INSERT INTO corpus.passages (faiss_id, fichier_source, page, content, entreprise,"
            " secteur, type_document, is_synthetic, departement, departements, allowed_roles,"
            " access_roles, extra) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
            (i, m.get("fichier_source"), entier(m.get("page")), propre(m.get("content")),
             m.get("entreprise"), m.get("secteur"), m.get("type_document"),
             m.get("is_synthetic"), m.get("departement"), m.get("departements"),
             m.get("allowed_roles"), m.get("access_roles"), jdump(extra)))

    for k in kpi:
        cur.execute(
            "INSERT INTO corpus.kpi (id, entreprise, indicateur, libelle, annee, valeur, unite,"
            " record) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
            (k.get("id"), k.get("entreprise"), k.get("indicateur"), k.get("libelle"),
             entier(k.get("annee")), flottant(k.get("valeur")), k.get("unite"), jdump(k)))

    for c in cas:
        cur.execute(
            "INSERT INTO corpus.eval_cases (id, role, statut, question, expected_mode,"
            " expected_source, expected_contains, expected_departement, record)"
            " VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s,%s::jsonb)",
            (c.get("id"), c.get("role"), c.get("statut"), c.get("question"),
             jdump(c.get("expected_mode")), c.get("expected_source"),
             jdump(c.get("expected_contains")), c.get("expected_departement"), jdump(c)))

    conn.commit()

    # --- verification : comptages en base = comptages des fichiers ---
    attendu = {"documents": len(docs), "passages": len(metadata),
               "kpi": len(kpi), "eval_cases": len(cas)}
    ok = True
    print("%-12s %8s %8s" % ("table", "fichier", "base"))
    for t, n in attendu.items():
        cur.execute("SELECT count(*) FROM corpus." + t)
        en_base = cur.fetchone()[0]
        ok &= (en_base == n)
        print("%-12s %8d %8d  %s" % (t, n, en_base, "OK" if en_base == n else "ECART"))
    cur.execute("SELECT count(*) FROM corpus.documents WHERE sha256 IS NOT NULL")
    print("PDF retrouves dans data/raw : %d / %d" % (cur.fetchone()[0], len(docs)))
    conn.close()
    if not ok:
        sys.exit("ECART de comptage : import a verifier")
    print("Import termine.")


if __name__ == "__main__":
    main()
