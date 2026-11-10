/**
 * Panel del carrito: las líneas, el total y las acciones de cada línea.
 *
 * Todo lo que se muestra viene de la respuesta del backend —nombre, precio
 * unitario, subtotal y total—, igual que en ProductCards.jsx y en
 * ComparisonTable.jsx: el frontend no suma ni estima.
 *
 * Se actualiza sin recargar: cada acción devuelve el carrito entero y el
 * contexto reemplaza el anterior.
 */

import { formatPrice } from '../format.js'
import { useCart } from '../CartContext.jsx'
import { Empty } from './Notice.jsx'
import CartLine from './CartLine.jsx'

export default function CartPanel({ title = 'Tu carrito', editable = true, action = null }) {
  const { cart, error, pending, clearError } = useCart()

  return (
    <section className="cart-panel" aria-label={title}>
      <header className="cart-panel-header">
        <h3>{title}</h3>
        <span className="badge badge-neutral">{unitsLabel(cart.item_count)}</span>
      </header>

      {error ? (
        <p className="cart-error" role="alert">
          {error}
          <button type="button" className="button-secondary" onClick={clearError}>
            Entendido
          </button>
        </p>
      ) : null}

      {cart.items.length === 0 ? (
        <Empty title="El carrito está vacío">
          Agregá productos desde el catálogo o pedíselo al asistente.
        </Empty>
      ) : (
        <>
          <ul className="cart-lines">
            {cart.items.map((line) => (
              <CartLine
                key={line.product_id}
                line={line}
                editable={editable}
                pending={pending}
              />
            ))}
          </ul>

          <p className="cart-total">
            <span>Total</span>
            <strong>{formatPrice(cart.total, cart.currency)}</strong>
          </p>
        </>
      )}

      {action}
    </section>
  )
}

// Escribe cuántas unidades hay, con la concordancia correcta.
function unitsLabel(count) {
  if (!count) {
    return 'Sin unidades'
  }
  return count === 1 ? '1 unidad' : `${count} unidades`
}
