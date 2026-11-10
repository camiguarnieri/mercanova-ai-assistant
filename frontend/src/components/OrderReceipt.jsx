/**
 * Una orden confirmada: su identificador, cuándo se hizo y qué se compró.
 *
 * Lo usa el último paso del checkout (RF-14) y también el historial (RF-16),
 * así la orden se lee igual en los dos lugares.
 *
 * Los precios son los que quedaron guardados al confirmar, no los del catálogo
 * de ahora: eso es lo que el usuario compró, y por eso la orden los copia.
 */

import { formatDateTime, formatPrice } from '../format.js'

export default function OrderReceipt({ order, highlight = false }) {
  return (
    <article className={highlight ? 'order order-highlight' : 'order'}>
      <header className="order-header">
        <div>
          <p className="order-id">{order.order_id}</p>
          <p className="order-date">{formatDateTime(order.created_at)}</p>
        </div>
        <strong className="order-total">
          {formatPrice(order.total_amount, order.currency)}
        </strong>
      </header>

      <table className="order-items">
        <thead>
          <tr>
            <th scope="col">Producto</th>
            <th scope="col">Cantidad</th>
            <th scope="col">Precio unitario</th>
            <th scope="col">Subtotal</th>
          </tr>
        </thead>
        <tbody>
          {order.items.map((line) => (
            <tr key={line.product_id}>
              <th scope="row">
                {line.name}
                <span className="order-item-id">{line.product_id}</span>
              </th>
              <td>{line.quantity}</td>
              <td>{formatPrice(line.unit_price, line.currency)}</td>
              <td>{formatPrice(line.line_total, line.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="order-shipping">
        <dt>Recibe</dt>
        <dd>{order.customer_name}</dd>
        <dt>Dirección</dt>
        <dd>{order.shipping_address}</dd>
      </dl>
    </article>
  )
}
