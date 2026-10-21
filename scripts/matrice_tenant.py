import os
from rag.config import ROLES_DISPONIBLES
from rag.rbac import est_accessible
from rag.retrieval import load_index
from rag.tenancy import contexte_tenant

_, metadata = load_index()
roles = list(ROLES_DISPONIBLES)
print("%-10s" % "tenant" + "".join("%-12s" % r for r in roles))
for t in ("demo", "autre"):
    with contexte_tenant(t):
        print("%-10s" % t + "".join("%-12d" % sum(1 for c in metadata if est_accessible(c, r)) for r in roles))
