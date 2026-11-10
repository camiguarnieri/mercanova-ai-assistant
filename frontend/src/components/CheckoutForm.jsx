/**
 * Paso 2 del checkout: los datos de envío.
 *
 * Son los datos mínimos que pide la letra (RF-11, RF-13): nombre y dirección.
 * **No hay pasarela de pago ni campos de tarjeta**, y no los va a haber: el
 * backend tampoco los acepta.
 *
 * Este formulario no confirma la compra. Al continuar se pasa a la pantalla de
 * confirmación, que es la única que llama al checkout.
 */

import { useState } from 'react'

export default function CheckoutForm({ details, onBack, onContinue }) {
  const [customerName, setCustomerName] = useState(details.customerName)
  const [shippingAddress, setShippingAddress] = useState(details.shippingAddress)
  const [missing, setMissing] = useState(null)

  function handleSubmit(event) {
    event.preventDefault()
    const name = customerName.trim()
    const address = shippingAddress.trim()
    if (name === '' || address === '') {
      setMissing('Completá el nombre y la dirección de envío: los dos son obligatorios.')
      return
    }
    setMissing(null)
    onContinue({ customerName: name, shippingAddress: address })
  }

  return (
    <form className="checkout-form" onSubmit={handleSubmit}>
      <p className="checkout-step-hint">
        Son los únicos datos que pedimos. No hay pago: la compra es ficticia.
      </p>

      <label>
        Nombre de quien recibe
        <input
          type="text"
          value={customerName}
          onChange={(event) => setCustomerName(event.target.value)}
          maxLength={120}
          autoComplete="name"
          required
        />
      </label>

      <label>
        Dirección de envío
        <input
          type="text"
          value={shippingAddress}
          onChange={(event) => setShippingAddress(event.target.value)}
          maxLength={300}
          autoComplete="shipping street-address"
          required
        />
      </label>

      {missing ? (
        <p className="cart-inline-error" role="alert">
          {missing}
        </p>
      ) : null}

      <div className="checkout-actions">
        <button type="button" className="button-secondary" onClick={onBack}>
          Volver al carrito
        </button>
        <button type="submit">Revisar y confirmar</button>
      </div>
    </form>
  )
}
