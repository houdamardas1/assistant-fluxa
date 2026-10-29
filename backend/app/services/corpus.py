"""Statistiques du corpus visibles par un role (donnees reelles de l'index).

Seuls les chunks que le role a le droit de lire sont comptes : un profil ne
voit donc jamais la taille ni la liste des documents qui lui sont interdits."""

from collections import defaultdict
from typing import Callable, Iterable

from rag.classification import niveau_du_fichier


def _tri(compteur: dict, cle: str) -> list:
    return sorted(
        ({cle: nom, "chunks": v["chunks"], "files": len(v["files"])} for nom, v in compteur.items()),
        key=lambda x: (-x["chunks"], str(x[cle])),
    )


def corpus_stats(
    metadata: Iterable[dict],
    role: str,
    est_accessible: Callable[[dict, str], bool],
    departements_du_chunk: Callable[[dict], set],
) -> dict:
    fichiers: dict = {}
    par_entreprise = defaultdict(lambda: {"chunks": 0, "files": set()})
    par_departement = defaultdict(lambda: {"chunks": 0, "files": set()})
    par_type = defaultdict(lambda: {"chunks": 0, "files": set()})
    total = 0

    for chunk in metadata:
        if not est_accessible(chunk, role):
            continue

        total += 1
        nom = chunk.get("fichier_source") or "(sans nom)"
        type_doc = chunk.get("type_document", "entreprise")
        entreprise = chunk.get("entreprise")
        deps = sorted(departements_du_chunk(chunk))
        page = chunk.get("page")

        f = fichiers.setdefault(nom, {
            "file": nom, "entreprise": entreprise, "type": type_doc,
            "departements": set(), "chunks": 0, "max_page": 0,
            "demo": bool(chunk.get("is_synthetic")),
            "classification": niveau_du_fichier(chunk.get("fichier_source")),
        })
        f["chunks"] += 1
        f["departements"].update(deps)
        if isinstance(page, int):
            f["max_page"] = max(f["max_page"], page)

        par_type[type_doc]["chunks"] += 1
        par_type[type_doc]["files"].add(nom)
        if entreprise:
            par_entreprise[entreprise]["chunks"] += 1
            par_entreprise[entreprise]["files"].add(nom)
        for d in deps:
            par_departement[d]["chunks"] += 1
            par_departement[d]["files"].add(nom)

    liste = sorted(
        ({**f, "departements": sorted(f["departements"])} for f in fichiers.values()),
        key=lambda x: (-x["chunks"], x["file"]),
    )

    return {
        "role": role,
        "total_chunks": total,
        "total_files": len(liste),
        "total_pages": sum(f["max_page"] for f in liste),
        "by_company": _tri(par_entreprise, "name"),
        "by_department": _tri(par_departement, "name"),
        "by_type": _tri(par_type, "type"),
        "files": liste,
    }
