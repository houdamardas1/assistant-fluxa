import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// L'API FastAPI autorise http://localhost:5173 (CORS_ORIGINS du backend).
export default defineConfig({
  plugins: [react()],
  server: { host: 'localhost', port: 5173, strictPort: true },
  preview: { host: 'localhost', port: 5173, strictPort: true },
})
