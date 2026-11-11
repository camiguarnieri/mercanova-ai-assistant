import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Configuración de Vite: React, el puerto fijo que el backend habilita en CORS
// y los tests de componentes en jsdom.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.test.jsx'],
    setupFiles: ['./tests/setup.js'],
  },
})
