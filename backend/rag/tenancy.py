"""Isolation par tenant (organisation) dans la recherche.

Chaque passage appartient a un tenant. Les textes reglementaires publics sont
partages entre tous les tenants. Un passage d'un autre tenant est INVISIBLE :
il est ecarte avant tout calcul, donc il ne peut ni etre cite ni declencher un
message d'acces refuse (qui reveleraient son existence).

Le tenant de l'appelant est porte par une variable de contexte posee au niveau
de l'endpoint, a partir du jeton (jamais du corps de la requete). Sans contexte
(scripts, diagnostics), on retombe sur le tenant du corpus."""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

TENANT_CORPUS = os.getenv("CORPUS_TENANT_ID", "demo")
TYPES_PARTAGES = {"public_reglementaire"}

_courant: ContextVar = ContextVar("tenant_courant", default=None)


def tenant_courant() -> str:
    return _courant.get() or TENANT_CORPUS


def tenant_du_chunk(chunk: dict) -> str:
    return chunk.get("tenant_id") or TENANT_CORPUS


@contextmanager
def contexte_tenant(tenant: Optional[str]):
    jeton = _courant.set(tenant or None)
    try:
        yield
    finally:
        _courant.reset(jeton)


def visible_pour_tenant(chunk: dict, tenant: Optional[str] = None) -> bool:
    if chunk.get("type_document") in TYPES_PARTAGES:
        return True
    return tenant_du_chunk(chunk) == (tenant or tenant_courant())
