/** Tarjeta de un producto en el listado. */

import { formatPrice, formatStock } from '../format.js'
import AddToCartButton from './AddToCartButton.jsx'

// Muestra imagen, nombre, marca, precio y stock. Toda la tarjeta abre la ficha;
// el botón queda para quien navega con teclado.
export default function ProductCard({ product, onSelect }) {
  const withoutStock = product.available_qty === 0

  function open(event) {
    event.stopPropagation()
    onSelect(product.product_id)
  }

  return (
    <article className="card" onClick={() => onSelect(product.product_id)}>
      <img
        className="card-image"
        src={product.image_url}
        alt={product.name}
        loading="lazy"
        width="280"
        height="170"
      />
      <div className="card-body">
        <h3 className="card-name">{product.name}</h3>
        <p className="card-brand">
          {product.brand} · {product.category}
        </p>
        <p className="card-price">{formatPrice(product.current_price, product.currency)}</p>
        <span className={withoutStock ? 'badge badge-alert card-stock' : 'badge badge-neutral card-stock'}>
          {formatStock(product.available_qty)}
        </span>
        <button type="button" onClick={open}>
          Ver detalle
        </button>
        {/* Sin stock el botón queda deshabilitado: el dato es el mismo que
            imprime la etiqueta de arriba, y sale del catálogo. */}
        <AddToCartButton
          productId={product.product_id}
          inStock={!withoutStock}
          className="card-add"
        />
      </div>
    </article>
  )
}
