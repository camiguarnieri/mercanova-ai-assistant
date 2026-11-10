/** Vista de ficha: todos los datos del detalle de un producto. */

import { useCallback, useEffect, useState } from 'react'

import { fetchProduct } from '../api/client.js'
import { ErrorNotice, Loading } from '../components/Notice.jsx'
import SpecificationGroups from '../components/SpecificationGroups.jsx'
import { MISSING, formatPrice, formatStock, splitList } from '../format.js'
import AddToCartButton from '../components/AddToCartButton.jsx'

export default function ProductDetail({ productId, onBack }) {
  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchProduct(productId)
      .then((result) => {
        if (!cancelled) {
          setProduct(result)
        }
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause.message)
          setProduct(null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [productId])

  useEffect(load, [load])

  return (
    <section className="detail">
      <button type="button" className="button-secondary" onClick={onBack}>
        ← Volver al listado
      </button>

      {loading ? (
        <Loading title="Cargando la ficha del producto...">
          Consultando el catálogo.
        </Loading>
      ) : null}
      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {!loading && !error && product ? <ProductSheet product={product} /> : null}
    </section>
  )
}

// Arma la ficha con los datos que devolvió la API.
function ProductSheet({ product }) {
  const withoutStock = product.available_qty === 0

  return (
    <article>
      <header className="detail-header">
        <img
          className="detail-image"
          src={product.image_url}
          alt={product.name}
          width="320"
          height="240"
        />
        <div className="detail-summary">
          <h2>{product.name}</h2>
          <p className="detail-brand">
            {product.brand} · {product.category} / {product.subcategory}
          </p>
          <p className="detail-price">{formatPrice(product.current_price, product.currency)}</p>
          {product.list_price && product.discount_percent ? (
            <p className="detail-list-price">
              <s>{formatPrice(product.list_price, product.currency)}</s>
              {product.discount_percent}% de descuento
            </p>
          ) : null}
          <span
            className={
              withoutStock ? 'badge badge-alert detail-stock' : 'badge badge-neutral detail-stock'
            }
          >
            {withoutStock ? 'Sin stock en ningún depósito' : formatStock(product.available_qty)}
          </span>
          {!product.active ? (
            <span className="badge badge-alert detail-inactive">
              Dado de baja del catálogo
            </span>
          ) : null}
          {/* Un producto dado de baja tampoco se puede comprar: el backend lo
              rechaza, así que el botón no lo ofrece. */}
          <AddToCartButton
            productId={product.product_id}
            inStock={!withoutStock && product.active}
            className="detail-add"
          />
        </div>
      </header>

      <p className="detail-description">{product.description || MISSING}</p>

      <Tags label="Recomendado para" text={product.recommended_for} />
      <Tags label="No recomendado para" text={product.not_recommended_for} />
      <Tags label="Características" text={product.key_features} />
      <Tags label="Etiquetas" text={product.tags} />

      <h3 className="detail-section-title">Datos del producto</h3>
      <dl className="detail-facts">
        <Fact label="Identificador" value={product.product_id} />
        <Fact label="SKU" value={product.sku} />
        <Fact label="Color" value={product.color} />
        <Fact label="Peso" value={withUnit(product.weight_kg, 'kg')} />
        <Fact label="Garantía" value={withUnit(product.warranty_months, 'meses')} />
        <Fact label="Devolución" value={withUnit(product.return_days, 'días')} />
        <Fact
          label="Puntaje"
          value={
            present(product.rating)
              ? `${product.rating} de 5 (${product.review_count ?? 0} reseñas)`
              : null
          }
        />
        <Fact label="Lanzamiento" value={product.launch_date} />
        <Fact
          label="Impuestos"
          value={product.tax_included === null ? null : product.tax_included ? 'Incluidos' : 'No incluidos'}
        />
        <Fact label="Precio actualizado" value={product.price_updated_at} />
      </dl>

      <h3 className="detail-section-title">Especificaciones</h3>
      <SpecificationGroups specifications={product.specifications} />
    </article>
  )
}

// Dice si el catálogo trae el dato. El 0 es un valor, no una ausencia: con un
// `valor ? ... : null` un puntaje de 0 o una garantía de 0 meses se mostrarían
// como "Sin dato", que es afirmar algo distinto de lo que dice el catálogo.
function present(value) {
  return value !== null && value !== undefined && value !== ''
}

// Pega la unidad al valor, si el catálogo lo trae.
function withUnit(value, unit) {
  return present(value) ? `${value} ${unit}` : null
}

// Muestra un dato suelto, o avisa que el catálogo no lo tiene.
function Fact({ label, value }) {
  return (
    <div className="detail-fact">
      <dt>{label}</dt>
      <dd>{value === null || value === undefined || value === '' ? MISSING : value}</dd>
    </div>
  )
}

// Muestra una lista separada por punto y coma como etiquetas.
function Tags({ label, text }) {
  const items = splitList(text)
  if (items.length === 0) {
    return null
  }
  return (
    <p className="detail-tags">
      <span className="detail-tags-label">{label}</span>
      {items.map((item) => (
        <span key={item} className="tag">
          {item}
        </span>
      ))}
    </p>
  )
}
