/**
 * Tarjetas de los productos que devolvió una búsqueda del asistente.
 *
 * Se arman con el payload de la herramienta, no con el texto del modelo: el
 * precio, el stock y los usos recomendados los imprime el sistema, así deja de
 * importar lo que el modelo escriba sobre ellos. Mismo criterio que
 * ComparisonTable.jsx y que la traza de herramientas.
 */

import { MISSING_USES, formatPrice, splitList } from '../format.js'
import AddToCartButton from './AddToCartButton.jsx'

export default function ProductCards({ products }) {
  if (!products || products.length === 0) {
    return null
  }

  return (
    <section className="chat-products" aria-label="Productos del catálogo">
      {products.map((product) => (
        <article key={product.product_id} className="chat-product">
          <p className="chat-product-name">{product.name}</p>
          <p className="chat-product-brand">
            {product.brand} · {product.product_id}
          </p>
          <p className="chat-product-price">
            {formatPrice(product.current_price, product.currency)}
          </p>
          <span
            className={
              product.in_stock ? 'badge badge-neutral' : 'badge badge-alert'
            }
          >
            {product.in_stock ? 'Con stock' : 'Sin stock'}
          </span>
          <Uses label="Recomendado para" text={product.recommended_for} />
          <Uses label="No recomendado para" text={product.not_recommended_for} />
          {/* El usuario puede agregar lo que le mostró el asistente sin
              escribirle: el stock viene del mismo resultado de la búsqueda. */}
          <AddToCartButton productId={product.product_id} inStock={product.in_stock} />
        </article>
      ))}
    </section>
  )
}

// Muestra los usos del catálogo, o aclara que ese campo está vacío.
function Uses({ label, text }) {
  // El campo vacío llega con la frase ya escrita del backend, que es la misma
  // que recibió el modelo: acá se la reconoce para mostrarla como hueco y no
  // como un uso más.
  const items = text === MISSING_USES ? [] : splitList(text)
  return (
    <p className="chat-product-uses">
      <span className="chat-product-uses-label">{label}</span>
      {items.length === 0 ? (
        // El campo vacío se dice: en las pruebas el modelo lo completaba con el
        // valor de otro producto.
        <span className="chat-product-uses-empty">{MISSING_USES}</span>
      ) : (
        items.map((item) => (
          <span key={item} className="tag">
            {item}
          </span>
        ))
      )}
    </p>
  )
}
