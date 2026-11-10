/**
 * Botón para agregar un producto al carrito.
 *
 * Lo usan las tarjetas del catálogo y las del chat, así que el estado de
 * "agregando" y el mensaje de error viven acá y no se repiten en cada tarjeta.
 *
 * Sin stock el botón queda deshabilitado: el dato sale del catálogo, igual que
 * la etiqueta de stock que la tarjeta ya muestra. Si el backend rechaza por
 * otro motivo —el stock cambió, el producto se dio de baja—, el mensaje que
 * devolvió se muestra debajo del botón en vez de perderse.
 */

import { useState } from 'react'

import { useCart } from '../CartContext.jsx'

export default function AddToCartButton({ productId, inStock, className = '' }) {
  const { addItem } = useCart()
  const [adding, setAdding] = useState(false)
  const [added, setAdded] = useState(false)
  const [failure, setFailure] = useState(null)

  async function handleClick(event) {
    // La tarjeta del catálogo abre la ficha al hacer clic: este botón no.
    event.stopPropagation()
    setAdding(true)
    setFailure(null)
    const result = await addItem(productId, 1)
    setAdding(false)
    if (result.ok) {
      setAdded(true)
      return
    }
    setAdded(false)
    setFailure(result.message)
  }

  return (
    <>
      <button
        type="button"
        className={`button-secondary ${className}`.trim()}
        onClick={handleClick}
        disabled={!inStock || adding}
        title={inStock ? undefined : 'Sin stock disponible en el catálogo'}
      >
        {label(inStock, adding, added)}
      </button>
      {failure ? (
        <p className="cart-inline-error" role="alert">
          {failure}
        </p>
      ) : null}
    </>
  )
}

// Decide qué dice el botón según el estado en el que está.
function label(inStock, adding, added) {
  if (!inStock) {
    return 'Sin stock'
  }
  if (adding) {
    return 'Agregando...'
  }
  return added ? 'Agregado ✓' : 'Agregar al carrito'
}
