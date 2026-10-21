"""Matrice reelle : document, niveau, roles autorises (index local)."""
import collections
import json

from rag.classification import niveau_du_chunk
from rag.config import ROLES_DISPONIBLES
from rag.rbac import effective_allowed_roles

m = json.load(open("data/index/metadata.json", encoding="utf-8"))
m = m if isinstance(m, list) else list(m.values())
docs = collections.OrderedDict()
for c in m:
    docs.setdefault(c["fichier_source"], []).append(c)
print("%-40s %-13s %s" % ("document", "niveau", "roles autorises"))
for nom, chunks in docs.items():
    roles = set().union(*(effective_allowed_roles(c) for c in chunks))
    print("%-40s %-13s %s" % (nom, niveau_du_chunk(chunks[0]), ", ".join(r for r in ROLES_DISPONIBLES if r in roles)))
