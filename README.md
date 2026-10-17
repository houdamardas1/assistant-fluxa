# Morocco Enterprise Intelligence — interface web

React 18 + TypeScript + Vite + Tailwind + framer-motion. Toutes les donnees viennent de l'API FastAPI.

    npm install
    copy .env.example .env      # VITE_API_URL=http://127.0.0.1:8000
    npm run dev                 # http://localhost:5173
    npm run build               # production (dossier dist/)
    npm run typecheck

Le backend doit tourner (python -m uvicorn app.main:app --host 127.0.0.1 --port 8000).
