/**
 * Historial de órdenes de la sesión (RF-16).
 *
 * Las órdenes las guarda el servidor en la base, así que sobreviven a una
 * recarga mientras el navegador mantenga el mismo `session_id`. Si se pierde
 * el identificador, se pierde el acceso al historial: está dicho en la
 * pantalla para que no parezca que las órdenes se borraron.
 */

import { useCallback, useEffect, useState } from 'react'

import { fetchOrders } from '../api/cart.js'
import { useCart } from '../CartContext.jsx'
import { Empty, ErrorNotice, Loading } from './Notice.jsx'
import OrderReceipt from './OrderReceipt.jsx'

export default function OrderHistory({ reloadKey = 0 }) {
  const { sessionId } = useCart()
  const [orders, setOrders] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setOrders(await fetchOrders(sessionId))
    } catch (cause) {
      setError(cause.message)
    }
  }, [sessionId])

  // Se vuelve a pedir cuando cambia `reloadKey`: la pasa el checkout al
  // confirmar, así la orden nueva aparece sin recargar la página.
  useEffect(() => {
    load()
  }, [load, reloadKey])

  if (error) {
    return <ErrorNotice title="No se pudo traer el historial" message={error} onRetry={load} />
  }
  if (orders === null) {
    return <Loading title="Buscando tus órdenes..." />
  }
  if (orders.length === 0) {
    return (
      <Empty title="Todavía no compraste nada">
        Cuando confirmes una compra, la orden va a quedar listada acá con su identificador.
      </Empty>
    )
  }

  return (
    <div className="orders">
      <p className="orders-count">
        {orders.length === 1 ? '1 orden en esta sesión' : `${orders.length} órdenes en esta sesión`}
      </p>
      {orders.map((order) => (
        <OrderReceipt key={order.order_id} order={order} />
      ))}
    </div>
  )
}
