/**
 * Raíz de la aplicación: las pestañas y qué vista se muestra.
 *
 * Hay dos pestañas, catálogo y chat, y se cambia con un estado. No se usa un
 * router para no agregar una dependencia por dos pantallas.
 */

import { useState } from 'react'

import Chat from './pages/Chat.jsx'
import ProductDetail from './pages/ProductDetail.jsx'
import ProductList from './pages/ProductList.jsx'

const CATALOG = 'catalog'
const CHAT = 'chat'

/** Qué dice cada pestaña y qué se aclara abajo del título. */
const TABS = [
  { id: CATALOG, label: 'Catálogo', subtitle: 'Catálogo de productos' },
  { id: CHAT, label: 'Chat', subtitle: 'Asistente de compras' },
]

export default function App() {
  const [tab, setTab] = useState(CATALOG)
  // Si hay un id seleccionado se muestra la ficha; si no, el listado.
  const [selectedId, setSelectedId] = useState(null)

  const current = TABS.find((option) => option.id === tab)

  return (
    <div className="app">
      <header className="header">
        <h1>MercaNova</h1>
        <p className="header-subtitle">{current.subtitle}</p>
        <nav className="tabs" aria-label="Secciones">
          {TABS.map((option) => (
            <button
              key={option.id}
              type="button"
              className={option.id === tab ? 'tab tab-active' : 'tab'}
              aria-current={option.id === tab ? 'page' : undefined}
              onClick={() => setTab(option.id)}
            >
              {option.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Las dos vistas quedan montadas: cambiar de pestaña no borra la
          conversación del chat ni los filtros del catálogo. */}
      <main>
        <div hidden={tab !== CATALOG}>
          {selectedId === null ? (
            <ProductList onSelect={setSelectedId} />
          ) : (
            <ProductDetail productId={selectedId} onBack={() => setSelectedId(null)} />
          )}
        </div>
        <div hidden={tab !== CHAT}>
          <Chat />
        </div>
      </main>
    </div>
  )
}
