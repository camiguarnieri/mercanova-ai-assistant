/**
 * Raíz de la aplicación: las pestañas y qué vista se muestra.
 *
 * Hay tres pestañas —catálogo, chat y carrito— y se cambia con un estado. No
 * se usa un router para no agregar una dependencia por tres pantallas.
 *
 * El carrito está arriba de todo en un contexto porque lo tocan las tres: el
 * botón de cada tarjeta del catálogo, el asistente desde el chat y el checkout.
 */

import { useState } from 'react'

import { CartProvider, useCart } from './CartContext.jsx'
import Cart from './pages/Cart.jsx'
import Chat from './pages/Chat.jsx'
import ProductDetail from './pages/ProductDetail.jsx'
import ProductList from './pages/ProductList.jsx'

const CATALOG = 'catalog'
const CHAT = 'chat'
const CART = 'cart'

/** Qué dice cada pestaña y qué se aclara abajo del título. */
const TABS = [
  { id: CATALOG, label: 'Catálogo', subtitle: 'Catálogo de productos' },
  { id: CHAT, label: 'Chat', subtitle: 'Asistente de compras' },
  { id: CART, label: 'Carrito', subtitle: 'Carrito y órdenes' },
]

export default function App() {
  return (
    <CartProvider>
      <Shell />
    </CartProvider>
  )
}

// Las pestañas y las vistas, ya con el carrito disponible.
function Shell() {
  const { cart } = useCart()
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
              {/* La cuenta sale del carrito del servidor, no de un contador
                  propio: es el mismo número que muestra el panel. */}
              {option.id === CART && cart.item_count > 0 ? (
                <span className="tab-count">{cart.item_count}</span>
              ) : null}
            </button>
          ))}
        </nav>
      </header>

      {/* Las tres vistas quedan montadas: cambiar de pestaña no borra la
          conversación del chat, los filtros del catálogo ni el paso del
          checkout en el que estaba el usuario. */}
      <main>
        <div hidden={tab !== CATALOG}>
          {selectedId === null ? (
            <ProductList onSelect={setSelectedId} />
          ) : (
            <ProductDetail productId={selectedId} onBack={() => setSelectedId(null)} />
          )}
        </div>
        <div hidden={tab !== CHAT}>
          <Chat onGoToCart={() => setTab(CART)} />
        </div>
        <div hidden={tab !== CART}>
          <Cart />
        </div>
      </main>
    </div>
  )
}
