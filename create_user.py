#!/usr/bin/env python3
"""
Gestion des comptes utilisateurs (base SQLite data/users.db).

    python create_user.py --username alice --role finance --tenant demo --name "Alice B."
    python create_user.py --demo                  # un compte par role, mots de passe aleatoires
    python create_user.py --list
    python create_user.py --reset-password alice
    python create_user.py --deactivate alice      (ou --activate alice)

Le mot de passe est saisi sans affichage (jamais en argument de ligne de
commande). Avec --demo, des mots de passe ALEATOIRES sont generes et affiches
UNE seule fois : notez-les, ils ne sont pas recuperables (seul le hash est stocke).
"""

import argparse
import getpass
import secrets
import sys

from app.core.config import settings
from app.services.users import MIN_PASSWORD, UserStore
from rag.config import ROLES_DISPONIBLES


def saisir_mot_de_passe() -> str:
    while True:
        a = getpass.getpass(f"Mot de passe ({MIN_PASSWORD}+ caracteres) : ")
        b = getpass.getpass("Confirmation : ")
        if a != b:
            print("Les deux saisies different.", file=sys.stderr)
            continue
        return a


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=settings.USERS_DB_PATH)
    ap.add_argument("--username")
    ap.add_argument("--role", choices=ROLES_DISPONIBLES)
    ap.add_argument("--tenant", default="demo")
    ap.add_argument("--name")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--reset-password", metavar="USERNAME")
    ap.add_argument("--deactivate", metavar="USERNAME")
    ap.add_argument("--activate", metavar="USERNAME")
    args = ap.parse_args()

    store = UserStore(args.db, ROLES_DISPONIBLES)

    if args.list:
        for u in store.list_users():
            etat = "actif" if u.active else "DESACTIVE"
            print(f"{u.username:20s} {u.role:10s} tenant={u.tenant_id:10s} {etat}  ({u.display_name})")
        return 0

    for cible, actif in ((args.deactivate, False), (args.activate, True)):
        if cible:
            ok = store.set_active(cible, actif)
            print("OK" if ok else "Utilisateur introuvable.")
            return 0 if ok else 1

    if args.reset_password:
        if not store.get(args.reset_password):
            print("Utilisateur introuvable.", file=sys.stderr)
            return 1
        store.set_password(args.reset_password, saisir_mot_de_passe())
        print("Mot de passe modifie.")
        return 0

    if args.demo:
        print("Comptes de demonstration (mots de passe affiches UNE SEULE FOIS) :\n")
        for role in ROLES_DISPONIBLES:
            mot_de_passe = secrets.token_urlsafe(12)
            try:
                store.create_user("demo_" + role, mot_de_passe, role, args.tenant,
                                  f"Profil {role.capitalize()}")
                print(f"  demo_{role:12s} {mot_de_passe}")
            except ValueError as e:
                print(f"  {role:12s} (ignore : {e})")
        return 0

    if not (args.username and args.role):
        ap.error("--username et --role sont requis (ou --demo / --list).")

    try:
        u = store.create_user(args.username, saisir_mot_de_passe(), args.role,
                              args.tenant, args.name)
    except ValueError as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 1
    print(f"Compte cree : {u.username} ({u.role}, tenant {u.tenant_id}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
