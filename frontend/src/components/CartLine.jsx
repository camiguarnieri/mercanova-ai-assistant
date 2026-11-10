/**
 * Una línea del carrito, con sus controles de cantidad.
 *
 * La cantidad se puede escribir, y antes de mandarla se revisa que sea un
 * entero mayor a 0: ese mensaje lo escribe el frontend porque es la misma
 * regla que aplica `cart.check_quantity()` en el backend, y así el usuario la
 * lee en español sin esperar el viaje. Todo lo demás —stock, precio, total— lo
 * decide el backend, y su mensaje se muestra tal cual.
 */

import { useEffect, useState } from 'react'

import { formatPrice } from '../format.js'
import { useCart } from '../CartContext.jsx'

/** Lo que se le dice al usuario si escribe una cantidad que no sirve. */
export const INVALID_QUANTITY = 'La cantidad tiene que ser un número entero mayor a 0.'

export default function CartLine({ line, editable, pending }) {
  const { setQuantity, removeItem } = useCart()
  const [draft, setDraft] = useState(String(line.quantity))
  const [invalid, setInvalid] = useState(null)

  // Si el carrito vuelve del servidor con otra cantidad —la cambió el
  // asistente, o se agregó la misma línea de nuevo—, el campo la refleja.
  useEffect(() => {
    setDraft(String(line.quantity))
  }, [line.quantity])

  // Manda la cantidad escrita, si es un entero mayor a 0.
  async function commit() {
    const wanted = Number(draft)
    if (!Number.isInteger(wanted) || wanted <= 0 || draft.trim() === '') {
      setInvalid(INVALID_QUANTITY)
      return
    }
    setInvalid(null)
    if (wanted === line.quantity) {
      return
    }
    const result = await setQuantity(line.product_id, wanted)
    if (!result.ok) {
      // El backend rechazó: se vuelve a lo que hay guardado y su mensaje lo
      // muestra el panel.
      setDraft(String(line.quantity))
    }
  }

  // Suma o resta una unidad, sin pasar del stock disponible.
  function step(delta) {
    setInvalid(null)
    setQuantity(line.product_id, line.quantity + delta)
  }

  const short = line.available_qty < line.quantity

  return (
    <li className="cart-line">
      <div className="cart-line-product">
        <p className="cart-line-name">{line.name}</p>
        <p className="cart-line-meta">
          {line.brand} · {line.product_id}
        </p>
        <p className="cart-line-meta">
          {formatPrice(line.unit_price, line.currency)} por unidad
        </p>
        {short ? (
          <span className="badge badge-alert" role="status">
            Quedan {line.available_qty} en stock
          </span>
        ) : null}
      </div>

      {editable ? (
        <div className="cart-line-quantity">
          <button
            type="button"
            className="button-secondary cart-step"
            onClick={() => step(-1)}
            disabled={pending || line.quantity <= 1}
            aria-label={`Quitar una unidad de ${line.name}`}
          >
            −
          </button>
          <input
            type="number"
            min="1"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                commit()
              }
            }}
            disabled={pending}
            aria-label={`Cantidad de ${line.name}`}
          />
          <button
            type="button"
            className="button-secondary cart-step"
            onClick={() => step(1)}
            disabled={pending || line.quantity >= line.available_qty}
            aria-label={`Sumar una unidad de ${line.name}`}
            title={
              line.quantity >= line.available_qty
                ? 'No hay más unidades disponibles en el catálogo'
                : undefined
            }
          >
            +
          </button>
        </div>
      ) : (
        <p className="cart-line-quantity-fixed">{line.quantity} u.</p>
      )}

      <div className="cart-line-amount">
        <strong>{formatPrice(line.line_total, line.currency)}</strong>
        {editable ? (
          <button
            type="button"
            className="button-secondary"
            onClick={() => removeItem(line.product_id)}
            disabled={pending}
          >
            Quitar
          </button>
        ) : null}
      </div>

      {invalid ? (
        <p className="cart-inline-error" role="alert">
          {invalid}
        </p>
      ) : null}
    </li>
  )
}
