# Environnements : dev, staging, production

Un même `docker-compose.yml` sert de base ; staging et production ajoutent une
surcouche. Un seul environnement tourne à la fois (noms de conteneurs fixes) ;
l'option `-p` donne à chacun ses propres volumes, donc sa propre base.

| | dev | staging | production |
|---|---|---|---|
| Fichiers | `docker-compose.yml` (+ `docker-compose.dev.yml`) | + `docker-compose.staging.yml` | + `docker-compose.prod.yml` |
| Modèle de `.env` | `.env.example` | `env/staging.env.example` | `env/prod.env.example` |
| `DEBUG` | True | False | False |
| PostgreSQL exposé sur la machine | oui (127.0.0.1:15432) | non | non |
| pgAdmin | démarré | profil `tools` (à la demande) | profil `tools` (à la demande) |
| Redémarrage automatique | non | oui | oui |
| Limites de ressources | non | mémoire API 4 Go | mémoire API 4 Go / 2 CPU, PostgreSQL 1 Go |
| Secrets obligatoires (démarrage refusé sinon) | non | oui | oui |
| `localhost` toléré dans `CORS_ORIGINS` / `PUBLIC_API_URL` | oui | oui (répétition locale) | non (refusé par `verifier_env.py`) |

## Démarrer

    # dev
    docker compose up -d --build

    # staging
    python scripts/verifier_env.py .env
    docker compose -p fluxa-staging -f docker-compose.yml -f docker-compose.staging.yml up -d --build

    # production
    python scripts/verifier_env.py .env
    docker compose -p fluxa-prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build

`verifier_env.py` refuse un `.env` qui contient encore des valeurs d'exemple
(`CHANGE_ME`, `changez-moi`, clé factice), un `DEBUG` actif, une `SECRET_KEY`
de moins de 32 caractères, ou (production) une adresse `localhost`. Il
n'affiche que les noms des variables en cause, jamais leurs valeurs.

## Base vide (nouvel environnement)

1. Créer les utilisateurs : `create_user.py` dans le conteneur `api`.
2. Charger les jeux de données : `python scripts/import_datasets_pg.py` se
   connecte à 127.0.0.1:15432, fermé en staging/production par conception. Pour
   l'importer, démarrer temporairement PostgreSQL avec la base seule
   (`docker compose -p fluxa-staging -f docker-compose.yml up -d postgres`),
   lancer l'import, puis redémarrer avec la surcouche.

## Statut de validation

Les surcouches sont validées par `docker compose config` (syntaxe et variables
obligatoires), pas par un démarrage complet sur une machine distincte. Les
limites de mémoire sont des valeurs de départ à ajuster selon la machine cible.
Les secrets de production ne figurent jamais dans Git : ils vivent dans le
`.env` de la machine cible.
