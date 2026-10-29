# Fluxa : assistant documentaire IA sécurisé (RAG)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![FAISS](https://img.shields.io/badge/FAISS-recherche%20vectorielle-0467DF)
![Groq](https://img.shields.io/badge/LLM-Groq-F55036)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Azure Bicep](https://img.shields.io/badge/Azure-Bicep-0078D4?logo=microsoftazure&logoColor=white)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green)](LICENSE)

Fluxa répond aux questions des collaborateurs d'une entreprise à partir de ses propres
documents, **en respectant qui a le droit de voir quoi**. Chaque réponse cite ses sources,
chaque accès est tracé, et une question hors périmètre ou malveillante est refusée plutôt
qu'inventée.

> Conçu et développé par **[Houda Mardas](#auteure)**, AI Engineer, pendant son stage chez
> Alexsys Solutions (Casablanca, 2026).

## Résultats clés

| | |
|---|---|
| Corpus indexé | ~3 000 passages, réponses avec citation des sources |
| Évaluation sur le vrai pipeline | 55 cas, 100 % de réussite ([détail](backend/docs/EVALUATION.md)) |
| Injections de prompt | 9 / 9 bloquées (français, anglais, arabe, darija) |
| Accès interdits (RBAC) | 7 / 7 refusés, 8 rôles métier, 4 niveaux de classification |
| Tests automatisés | 229 tests, CI GitHub Actions avec analyse de secrets (gitleaks) |
| Déploiement | Docker, 3 environnements (dev, staging, prod), architecture Azure en 9 modules Bicep |

## Architecture

```mermaid
flowchart LR
    U[Navigateur] --> W[Interface web<br/>React + nginx :3000]
    W -->|HTTPS + JWT| A[API FastAPI :8000]
    A --> F[Filtre d'entrée<br/>injections]
    F --> R[Recherche hybride<br/>FAISS + lexical]
    R --> C[RBAC + classification<br/>+ tenant]
    C --> V[Vérification<br/>de pertinence]
    V --> L[(Groq LLM)]
    A --> P[(PostgreSQL<br/>audit)]
```

## Contenu du dépôt

| Dossier | Contenu |
|---|---|
| [`backend/`](backend) | API FastAPI, moteur RAG (recherche hybride, RBAC, filtre anti-injection, vérification), audit PostgreSQL, évaluation, tests, Docker Compose, modèles Bicep Azure |
| [`frontend/`](frontend) | Interface React + TypeScript : assistant avec sources citées, tableau de bord, indicateurs, documents, journal d'audit |

Chaque dossier a son propre README détaillé.

## Démarrage rapide (Docker)

Prérequis : Docker Desktop et une clé API Groq.

```bash
cd backend
cp .env.example .env          # renseigner GROQ_API_KEY et SECRET_KEY (32 caractères minimum)
docker compose up -d --build  # API, interface web et PostgreSQL
docker compose exec api python create_user.py --demo   # un compte par rôle
```

Interface web : http://localhost:3000 · API : http://localhost:8000

L'index FAISS se reconstruit avec `build_index.py` à partir de vos propres documents : le
corpus brut et l'index ne sont pas versionnés.

## Stack technique

- **IA / RAG** : sentence-transformers, FAISS, recherche hybride vectorielle + lexicale, Groq, vérification de pertinence, sécurité LLM
- **Backend** : Python 3.11, FastAPI, Pydantic, JWT
- **Frontend** : React 18, TypeScript, Vite, Tailwind CSS, framer-motion
- **Données** : PostgreSQL, SQLite, ingestion PDF / DOCX / XLSX / PPTX
- **DevOps** : Docker, Docker Compose, GitHub Actions, gitleaks, Azure Container Apps, Key Vault, Bicep

## Documentation

- [Scénario de démonstration](backend/docs/DEMO.md)
- [Évaluation du RAG](backend/docs/EVALUATION.md)
- [Environnements dev / staging / prod](backend/docs/ENVIRONNEMENTS.md)
- [Architecture Azure](backend/docs/ARCHITECTURE_AZURE.md)
- [Limites connues](backend/docs/LIMITES.md)

## Auteure

**Houda Mardas** · AI Engineer (IA générative, RAG, agents IA) · Ingénieure d'État en Génie
Informatique & IA (HESTIM, Casablanca)

J'ai conçu et développé Fluxa de bout en bout : moteur RAG et recherche hybride, contrôle
d'accès et filtre anti-injection, API FastAPI, jeu d'évaluation, tests et CI,
conteneurisation, architecture Azure et interface web React.

- GitHub : [@houdamardas1](https://github.com/houdamardas1)
- LinkedIn : [houda-m-567987243](https://www.linkedin.com/in/houda-m-567987243)
- Portfolio : [portfoliohouda-mardas.netlify.app](https://portfoliohouda-mardas.netlify.app)
