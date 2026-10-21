# Fluxa : interface web

React 18 + TypeScript + Vite + Tailwind + framer-motion. Toutes les données
viennent de l'API FastAPI du dépôt `fluxa-backend`, qui contient aussi la
présentation du projet, l'architecture et le scénario de démonstration.

    npm install
    copy .env.example .env      # VITE_API_URL=http://127.0.0.1:8000
    npm run dev                 # http://localhost:5173
    npm run build               # production (dossier dist/)
    npm run typecheck

Le backend doit tourner :

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

ou, avec Docker, `docker compose up -d --build` dans le dépôt backend (l'interface
est alors servie sur http://localhost:3000).
