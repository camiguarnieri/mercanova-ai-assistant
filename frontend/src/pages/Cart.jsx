/**
 * Vista del carrito: el checkout paso a paso y el historial de órdenes.
 *
 * Los pasos son cuatro y se muestran de a uno (RF-11, RF-12, RF-14):
 *
 * 1. `SUMMARY`  el resumen editable del carrito;
 * 2. `DETAILS`  nombre y dirección de envío;
 * 3. `CONFIRM`  la confirmación explícita, la única que llama al checkout;
 * 4. `DONE`     la orden confirmada, con su identificador.
 *
 * Del paso 2 al 4 no hay atajo: la llamada a `checkout()` está en un solo
 * lugar, el de la confirmación, y el backend rechaza el pedido que no traiga
 * `confirmed`. Saltear la pantalla no es algo que la interfaz impida por
 * diseño visual, es algo que el contrato no acepta.
 */

import { useState } from 'react'

import { checkout } from '../api/cart.js'
import { useCart } from '../CartContext.jsx'
import CartPanel from '../components/CartPanel.jsx'
import CheckoutConfirm from '../components/CheckoutConfirm.jsx'
import CheckoutForm from '../components/CheckoutForm.jsx'
import OrderHistory from '../components/OrderHistory.jsx'
import OrderReceipt from '../components/OrderReceipt.jsx'

const SUMMARY = 'summary'
const DETAILS = 'details'
const CONFIRM = 'confirm'
const DONE = 'done'

/** Qué se muestra arriba en cada paso, para que se vea dónde está el usuario. */
const STEPS = [
  { id: SUMMARY, label: 'Carrito' },
  { id: DETAILS, label: 'Envío' },
  { id: CONFIRM, label: 'Confirmación' },
  { id: DONE, label: 'Orden' },
]

const NO_DETAILS = { customerName: '', shippingAddress: '' }

export default function Cart() {
  const { cart, sessionId, afterCheckout } = useCart()
  const [step, setStep] = useState(SUMMARY)
  const [details, setDetails] = useState(NO_DETAILS)
  const [order, setOrder] = useState(null)
  const [failure, setFailure] = useState(null)
  const [sending, setSending] = useState(false)
  // Cambia cuando se confirma una orden, para que el historial la vuelva a pedir.
  const [confirmedCount, setConfirmedCount] = useState(0)

  // Confirma la compra. Es el único lugar del frontend que crea una orden.
  async function handleConfirm() {
    setSending(true)
    setFailure(null)
    try {
      const created = await checkout(sessionId, details)
      setOrder(created)
      setStep(DONE)
      setConfirmedCount((previous) => previous + 1)
      // El carrito quedó vacío en el servidor: se refleja en todas las vistas.
      afterCheckout()
    } catch (cause) {
      // Carrito vacío, stock que se fue o datos rechazados: el mensaje del
      // backend se muestra en la pantalla de confirmación, no se silencia.
      setFailure(cause.message)
    } finally {
      setSending(false)
    }
  }

  // Vuelve al principio para empezar otra compra.
  function startOver() {
    setOrder(null)
    setFailure(null)
    setDetails(NO_DETAILS)
    setStep(SUMMARY)
  }

  return (
    <section className="cart-page">
      <ol className="checkout-steps" aria-label="Pasos de la compra">
        {STEPS.map((option, index) => (
          <li
            key={option.id}
            className={option.id === step ? 'checkout-step checkout-step-active' : 'checkout-step'}
            aria-current={option.id === step ? 'step' : undefined}
          >
            <span className="checkout-step-number">{index + 1}</span>
            {option.label}
          </li>
        ))}
      </ol>

      {step === SUMMARY ? (
        <CartPanel
          title="Tu carrito"
          action={
            <div className="checkout-actions">
              <button
                type="button"
                onClick={() => setStep(DETAILS)}
                disabled={cart.items.length === 0}
                title={
                  cart.items.length === 0
                    ? 'Agregá al menos un producto para poder comprar'
                    : undefined
                }
              >
                Continuar con la compra
              </button>
            </div>
          }
        />
      ) : null}

      {step === DETAILS ? (
        <CheckoutForm
          details={details}
          onBack={() => setStep(SUMMARY)}
          onContinue={(confirmedDetails) => {
            setDetails(confirmedDetails)
            setStep(CONFIRM)
          }}
        />
      ) : null}

      {step === CONFIRM ? (
        <CheckoutConfirm
          details={details}
          pending={sending}
          failure={failure}
          onBack={() => setStep(DETAILS)}
          onConfirm={handleConfirm}
        />
      ) : null}

      {step === DONE && order !== null ? (
        <div className="checkout-done">
          <p className="checkout-done-title" role="status">
            Compra confirmada. Guardá el número de orden: <strong>{order.order_id}</strong>
          </p>
          <OrderReceipt order={order} highlight />
          <div className="checkout-actions">
            <button type="button" className="button-secondary" onClick={startOver}>
              Volver al carrito
            </button>
          </div>
        </div>
      ) : null}

      <section className="cart-history" aria-label="Historial de órdenes">
        <h3>Tus órdenes</h3>
        <p className="checkout-step-hint">
          Son las órdenes de esta sesión. Se guardan en el servidor, así que siguen acá si
          recargás la página.
        </p>
        <OrderHistory reloadKey={confirmedCount} />
      </section>
    </section>
  )
}
