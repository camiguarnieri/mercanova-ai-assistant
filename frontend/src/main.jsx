/** Punto de entrada del frontend: monta la aplicación en el DOM. */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App.jsx'
import './styles/tokens.css'
import './styles/catalog.css'
import './styles/detail.css'
import './styles/chat.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
