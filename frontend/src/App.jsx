/**
 * Raíz de la aplicación: decide qué vista se muestra.
 *
 * Hay dos vistas, listado y ficha, y se cambia con un estado. No se usa un
 * router para no agregar una dependencia por dos pantallas.
 */

import { useState } from 'react'

import ProductDetail from './pages/ProductDetail.jsx'
import ProductList from './pages/ProductList.jsx'

export default function App() {
  // Si hay un id seleccionado se muestra la ficha; si no, el listado.
  const [selectedId, setSelectedId] = useState(null)

  return (
    <div className="app">
      <header className="header">
        <h1>MercaNova</h1>
        <p className="header-subtitle">Catálogo de productos</p>
      </header>

      <main>
        {selectedId === null ? (
          <ProductList onSelect={setSelectedId} />
        ) : (
          <ProductDetail productId={selectedId} onBack={() => setSelectedId(null)} />
        )}
      </main>
    </div>
  )
}
