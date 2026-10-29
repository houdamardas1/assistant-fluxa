# Fluxa : interface web

![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?logo=tailwindcss&logoColor=white)

Interface web de **Fluxa**, un assistant documentaire IA sécurisé (RAG) qui répond aux
questions des collaborateurs d'une entreprise à partir de ses propres documents, avec
citation des sources, contrôle d'accès par rôle et journal d'audit.

Toutes les données viennent de l'API FastAPI du dossier
[`../backend`](../backend), qui contient aussi le moteur
RAG, l'architecture, l'évaluation et le scénario de démonstration.

> Conçu et développé par **[Houda Mardas](#auteure)**, AI Engineer, pendant son stage
> chez Alexsys Solutions (Casablanca, 2026).

## Fonctionnalités

- **Assistant** : conversation avec le RAG, réponses avec sources citées et niveau de
  classification (Public, Interne, Confidentiel, Restreint), historique des échanges,
  analyse d'un fichier joint (PDF, Word, Excel, PowerPoint, texte, CSV, image).
- **Tableau de bord** : activité (questions, modes de réponse, évolution dans le temps) et statistiques du corpus.
- **Indicateurs** : KPI et graphiques issus des documents de l'entreprise.
- **Documents** : corpus accessible au rôle connecté, avec classification.
- **Audit** : journal des questions et des accès, réservé au rôle `direction`.
- **Authentification JWT**, routes protégées par rôle, thème clair / sombre, animations
  (framer-motion).

## Stack technique

React 18, TypeScript, Vite, Tailwind CSS, React Router, framer-motion. Image Docker servie
par nginx. CI GitHub Actions : vérification des types, build de production et analyse de
secrets (gitleaks).

## Démarrage

    npm install
    copy .env.example .env      # VITE_API_URL=http://127.0.0.1:8000
    npm run dev                 # http://localhost:5173
    npm run build               # production (dossier dist/)
    npm run typecheck

Le backend doit tourner :

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

ou, avec Docker, `docker compose up -d --build` dans le dossier `backend/` (l'interface
est alors servie sur http://localhost:3000).

## Structure

| Dossier | Contenu |
|---|---|
| `src/pages/` | Connexion, Assistant, Tableau de bord, Indicateurs, Documents, Audit |
| `src/components/` | composants du chat (messages, pièce jointe, historique) et d'interface (graphiques, cartes KPI, badges) |
| `src/context/` | état d'authentification et de conversation |
| `src/hooks/` | santé de l'API, thème, chargements asynchrones, animations |
| `src/lib/` | client API typé et types partagés |

## Auteure

**Houda Mardas** · AI Engineer (IA générative, RAG, agents IA) · Ingénieure d'État en
Génie Informatique & IA (HESTIM, Casablanca)

- GitHub : [@houdamardas1](https://github.com/houdamardas1)
- LinkedIn : [houda-m-567987243](https://www.linkedin.com/in/houda-m-567987243)
- Portfolio : [portfoliohouda-mardas.netlify.app](https://portfoliohouda-mardas.netlify.app)
