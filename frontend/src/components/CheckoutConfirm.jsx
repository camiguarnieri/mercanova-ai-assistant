/**
 * Paso 3 del checkout: la confirmación explícita (RF-12).
 *
 * Es la única pantalla desde la que se llama al checkout, y el botón recién se
 * habilita cuando el usuario marca la casilla. Las dos garantías que hacen que
 * no se pueda saltear:
 *
 * - en la interfaz, al paso siguiente solo se llega desde este botón;
 * - en el backend, `CheckoutRequest.confirmed` es `Literal[True]`, así que un
 *   pedido sin la confirmación no valida y no crea nada, venga de donde venga.
 *
 * El resumen se muestra en modo lectura: acá no se cambian cantidades, para
 * que lo que el usuario confirma sea exactamente lo que se cobra.
 */

import { useState } from 'react'

import CartPanel from './CartPanel.jsx'

export default function CheckoutConfirm({ details, pending, failure, onBack, onConfirm }) {
  const [accepted, setAccepted] = useState(false)

  return (
    <div className="checkout-confirm">
      <CartPanel title="Esto es lo que vas a comprar" editable={false} />

      <dl className="checkout-shipping">
        <dt>Recibe</dt>
        <dd>{details.customerName}</dd>
        <dt>Dirección</dt>
        <dd>{details.shippingAddress}</dd>
      </dl>

      {failure ? (
        <p className="cart-error" role="alert">
          {failure}
        </p>
      ) : null}

      <label className="checkout-accept">
        <input
          type="checkbox"
          checked={accepted}
          onChange={(event) => setAccepted(event.target.checked)}
        />
        Confirmo que quiero comprar estos productos con estos datos de envío.
      </label>

      <div className="checkout-actions">
        <button
          type="button"
          className="button-secondary"
          onClick={onBack}
          disabled={pending}
        >
          Cambiar los datos
        </button>
        <button type="button" onClick={onConfirm} disabled={!accepted || pending}>
          {pending ? 'Confirmando...' : 'Confirmar la compra'}
        </button>
      </div>
    </div>
  )
}
