"""Audits RBAC et commandes de diagnostic (article, terme, departement)."""

from collections import Counter

from .config import (
    DEPARTEMENTS,
    DEPARTMENT_ACCESS_ROLES,
    RBAC_POLICY,
    ROLES_DISPONIBLES,
)
from .juridique import est_renvoi_article, est_titre_article
from .rbac import (
    departement_a_corpus_reel,
    departements_du_chunk,
    effective_allowed_roles,
)
from .textutils import _motif_terme


def audit_allowed_roles(metadata: list) -> None:
    """Couverture RBAC effective par entreprise."""
    entreprises: dict = {}

    for chunk in metadata:
        if chunk.get("type_document", "entreprise") == "public_reglementaire":
            continue
        entreprises.setdefault(chunk.get("entreprise", "?"), []).append(chunk)

    if not entreprises:
        return

    print("\nAudit RBAC effectif par entreprise :")

    for ent in sorted(entreprises):
        chunks = entreprises[ent]
        counts = Counter(
            role for c in chunks for role in effective_allowed_roles(c)
        )
        detail = ", ".join(f"{r}={counts.get(r, 0)}" for r in ROLES_DISPONIBLES)
        print(f"   {ent} ({len(chunks)} chunks) : {detail}")

    print("\nPolitique RBAC par entreprise :")
    for ent, roles in RBAC_POLICY.items():
        print(f"   {ent} -> {', '.join(sorted(roles))}")
    print()


def extended_audit_allowed_roles(metadata: list) -> list:
    """Audit RBAC effectif par DEPARTEMENT (un chunk multi-departements
    compte dans chacun). Retourne la liste des departements SANS document
    d'entreprise reel."""
    print("\nAudit RBAC effectif par département :")

    par_dept = {d: [] for d in DEPARTEMENTS}
    orphelins = 0

    for chunk in metadata:
        deps = departements_du_chunk(chunk)

        for d in deps:
            par_dept[d].append(chunk)

        if (
            not deps
            and chunk.get("type_document", "entreprise") != "public_reglementaire"
            and chunk.get("entreprise") not in RBAC_POLICY
        ):
            orphelins += 1

    for dept in DEPARTEMENTS:
        chunks = par_dept[dept]

        if not chunks:
            print(f"   {dept:10s} : 0 chunk indexé  /!\\ aucun document (data/{dept}/)")
            continue

        counts = Counter(
            role for c in chunks for role in effective_allowed_roles(c)
        )
        n_synth = sum(1 for c in chunks if c.get("is_synthetic"))
        n_regl = sum(
            1 for c in chunks
            if not c.get("is_synthetic")
            and c.get("type_document", "entreprise") == "public_reglementaire"
        )
        n_reel = len(chunks) - n_synth - n_regl

        alertes = []

        if counts.get(dept, 0) == 0:
            alertes.append("le rôle du département n'a accès à aucun de ses chunks")
        if n_synth == len(chunks):
            alertes.append("uniquement des données de démonstration")
        elif n_reel == 0:
            alertes.append("aucun document interne réel (textes réglementaires seulement)")

        detail = ", ".join(f"{r}={counts.get(r, 0)}" for r in ROLES_DISPONIBLES)
        alerte_txt = f"  /!\\ {' ; '.join(alertes)}" if alertes else ""

        print(
            f"   {dept:10s} ({len(chunks)} chunks : entreprise={n_reel}, "
            f"réglementaire={n_regl}, démo={n_synth}) : {detail}{alerte_txt}"
        )

    if orphelins:
        print(
            f"\n   /!\\ {orphelins} chunk(s) sans département ni entreprise "
            "couverte par RBAC_POLICY : droits dépendant uniquement de "
            "'allowed_roles' brut."
        )

    print("\nPolitique RBAC par département :")
    for dept, roles in DEPARTMENT_ACCESS_ROLES.items():
        print(f"   {dept} -> {', '.join(sorted(roles))}")
    print()

    return [d for d in DEPARTEMENTS if not departement_a_corpus_reel(metadata, d)]


def _apercu(content: str, taille: int = 160) -> str:
    return " ".join((content or "").split())[:taille]


def diagnostic_article(metadata: list, numero: str) -> None:
    """Le TEXTE de l'article existe-t-il dans l'index (ou seulement des
    renvois) ?"""
    titres, renvois = [], []

    for c in metadata:
        content = c.get("content", "")

        if not est_renvoi_article(content, numero):
            continue

        entree = (c.get("fichier_source"), c.get("page"), _apercu(content))
        (titres if est_titre_article(content, numero) else renvois).append(entree)

    print(f"\n{'=' * 60}\nDIAGNOSTIC : article {numero}\n{'=' * 60}")
    print(f"\nChunks portant le TITRE de l'article : {len(titres)}")

    for fichier, page, extrait in titres[:5]:
        print(f"  - {fichier} p.{page}\n    {extrait}")

    print(f"\nChunks contenant seulement un RENVOI : {len(renvois)}")

    for fichier, page, extrait in renvois[:5]:
        print(f"  - {fichier} p.{page}\n    {extrait}")

    if not titres:
        print(
            "\n/!\\ Aucun chunk ne porte le texte de cet article : le problème "
            "est en amont, dans le chunking du PDF."
        )

    print()


def diagnostic_terme(metadata: list, terme: str) -> None:
    """Cherche un terme metier dans TOUT l'index, hors scoring et RBAC."""
    motif = _motif_terme(terme)
    trouvailles = [c for c in metadata if motif.search(c.get("content", ""))]

    print(f"\n{'=' * 60}\nDIAGNOSTIC TERME : \"{terme}\"\n{'=' * 60}")
    print(f"\n{len(trouvailles)} chunk(s) contenant ce terme (ou variante) :")

    for c in trouvailles[:10]:
        texte = " ".join(c.get("content", "").split())
        m = motif.search(texte)
        debut = max(0, (m.start() if m else 0) - 60)

        print(
            f"  - {c.get('fichier_source')} p.{c.get('page')} "
            f"[{c.get('entreprise')}] (type={c.get('type_document', '?')}, "
            f"departement={c.get('departement', '?')}, "
            f"roles={c.get('allowed_roles', [])})"
            f"\n    ...{texte[debut:debut + 200]}..."
        )

    if not trouvailles:
        print(
            "\n/!\\ Aucun chunk ne contient ce terme : vérifie l'orthographe "
            "dans le document source ou l'absence réelle de l'information."
        )

    print()


def diagnostic_departement(metadata: list, dept: str) -> None:
    """Chunks rattaches a un departement, roles effectifs et extraits."""
    dept = dept.strip().lower()

    print(f"\n{'=' * 60}\nDIAGNOSTIC DEPARTEMENT : \"{dept}\"\n{'=' * 60}")

    if dept not in DEPARTEMENTS:
        print(f"/!\\ Département inconnu. Disponibles : {DEPARTEMENTS}\n")
        return

    chunks = [c for c in metadata if dept in departements_du_chunk(c)]
    print(f"\n{len(chunks)} chunk(s) rattaché(s) au département '{dept}'.")

    if not chunks:
        print(f"/!\\ Aucun chunk : corpus probablement non ingéré (data/{dept}/).\n")
        return

    print(f"Rôles attendus par défaut : {sorted(DEPARTMENT_ACCESS_ROLES[dept])}")

    for c in chunks[:8]:
        if c.get("is_synthetic"):
            nature = "DEMO"
        elif c.get("type_document", "entreprise") == "public_reglementaire":
            nature = "réglementaire"
        else:
            nature = "entreprise"

        print(
            f"  - [{nature}] {c.get('fichier_source')} p.{c.get('page')} "
            f"roles_effectifs={sorted(effective_allowed_roles(c))}"
            f"\n    ...{_apercu(c.get('content', ''))}..."
        )

    print()
