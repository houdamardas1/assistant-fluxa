#!/usr/bin/env python3
"""
Genere un jeton de TEST (authentification simulee du POC).

    python make_token.py --role finance --tenant demo --user alice
    python make_token.py --role direction --tenant demo --user admin --minutes 480

Utilisation : curl -H "Authorization: Bearer <jeton>" ...
Ce script est volontairement un OUTIL LOCAL, pas un endpoint : le serveur
n'expose aucun moyen de se fabriquer un jeton.
"""

import argparse
import sys

from app.core.config import settings
from app.security.auth import check_secret, create_access_token
from rag.config import ROLES_DISPONIBLES


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", required=True, choices=ROLES_DISPONIBLES)
    ap.add_argument("--tenant", default="demo")
    ap.add_argument("--user", default="test-user")
    ap.add_argument("--minutes", type=int, default=settings.JWT_TTL_MINUTES)
    args = ap.parse_args()

    avertissement = check_secret(settings.SECRET_KEY, settings.ENVIRONMENT)
    if avertissement:
        print(f"/!\\ {avertissement}", file=sys.stderr)

    print(create_access_token(args.user, args.tenant, args.role,
                              settings.SECRET_KEY, args.minutes))


if __name__ == "__main__":
    main()
