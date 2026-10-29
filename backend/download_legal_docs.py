#!/usr/bin/env python3
"""
Telecharge les VRAIS PDF officiels des textes reglementaires marocains,
un par departement - meme logique que download_reports.py pour la Finance.

Corrige un manque de rigueur signale : le script precedent
(generate_legal_reference_docs.py) ecrivait des paragraphes reformules
a la main, pas les vrais documents. Celui-ci telecharge les PDF originaux,
qui seront ensuite extraits et chunkes par ingest_reports.py comme n'importe
quel autre document.

A executer depuis backend/.

Usage:
    python download_legal_docs.py
"""

import os
from pathlib import Path
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; POC-stage-Alexsys/1.0)"}
OUTPUT_DIR = "data/raw"

# (secteur, entreprise/label, url_pdf, nom_fichier)
DOCUMENTS = [
    ("it", "Cadre_Reglementaire_Maroc",
     "https://www.dgssi.gov.ma/sites/default/files/publications/pdf/2023-02/directive_nationale_de_la_securite_si_vf_12012023-3.pdf",
     "DNSSI_Directive_Securite_SI.pdf"),
    ("rh", "Cadre_Reglementaire_Maroc",
     "https://adala.justice.gov.ma/api/uploads/2024/04/30/code%20du%20travail-1714463246806.pdf",
     "Code_du_Travail_Loi_65-99.pdf"),
    ("commerce", "Cadre_Reglementaire_Maroc",
     "https://oriental.eregulations.org/media/code%20de%20commerce%20marocain.pdf",
     "Code_de_Commerce_Loi_15-95.pdf"),
    ("juridique", "Cadre_Reglementaire_Maroc",
     "https://rabat.eregulations.org/media/doc%20maroc.pdf",
     "Code_Obligations_Contrats_DOC.pdf"),
    ("marketing", "Cadre_Reglementaire_Maroc",
     "https://www.onssa.gov.ma/wp-content/uploads/2022/06/Reglementation/C.Reglementation-Connexe/4.%20Divers/LOI.31-08.FR.pdf",
     "Loi_31-08_Protection_Consommateur.pdf"),
]


def download_file(url: str, dest_path: str):
    if os.path.exists(dest_path):
        print(f"  deja telecharge : {dest_path}")
        return
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        content = resp.content
        if b"%PDF" not in content[:1024]:
            print(f"  ATTENTION : le contenu recu ne ressemble pas a un PDF valide pour {url}")
            return
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(content)
        print(f"  telecharge : {dest_path} ({len(content) / 1_000_000:.1f} Mo)")
    except Exception as e:
        print(f"  Erreur telechargement {url} : {e}")


def main():
    for secteur, entreprise, url, filename in DOCUMENTS:
        print(f"\n=== {entreprise} ({secteur}) ===")
        dest = os.path.join(OUTPUT_DIR, secteur, entreprise, filename)
        download_file(url, dest)

    print("\nTermine. Prochaine etape :")
    print("  1. Supprime les anciens fichiers *_chunks.json (contenu reformule) :")
    print("     Remove-Item data\\raw\\it\\Cadre_Reglementaire_Maroc\\*_chunks.json")
    print("     Remove-Item data\\raw\\rh\\Cadre_Reglementaire_Maroc\\*_chunks.json")
    print("     Remove-Item data\\raw\\commerce\\Cadre_Reglementaire_Maroc\\*_chunks.json")
    print("     Remove-Item data\\raw\\juridique\\Cadre_Reglementaire_Maroc\\*_chunks.json")
    print("     Remove-Item data\\raw\\marketing\\Cadre_Reglementaire_Maroc\\*_chunks.json")
    print("  2. Relance ingest_reports.py (apres avoir etendu SECTOR_ROLES)")
    print("  3. Relance build_index.py")


if __name__ == "__main__":
    main()