import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Configuración de Vite: React y el puerto fijo que el backend habilita en CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
})
