/** Vista de listado: filtros, tarjetas y paginación. */

import { useCallback, useEffect, useState } from 'react'

import { fetchBrands, fetchCategories, fetchProducts } from '../api/client.js'
import Filters, { EMPTY_FILTERS } from '../components/Filters.jsx'
import Pagination from '../components/Pagination.jsx'
import ProductCard from '../components/ProductCard.jsx'
import { Empty, ErrorNotice, Loading } from '../components/Notice.jsx'

/** Productos por página, dentro del máximo que acepta la API. */
const PAGE_SIZE = 12

export default function ProductList({ onSelect }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Las opciones de los filtros salen de la API, no están escritas a mano.
  const [options, setOptions] = useState({ categories: [], brands: [] })

  // Trae las opciones de los selects una sola vez.
  useEffect(() => {
    Promise.all([fetchCategories(), fetchBrands()])
      .then(([categories, brands]) => setOptions({ categories, brands }))
      .catch(() => setOptions({ categories: [], brands: [] }))
  }, [])

  // Vuelve a pedir la página cada vez que cambian los filtros o el offset.
  const load = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchProducts({ ...filters, limit: PAGE_SIZE, offset })
      .then((result) => {
        if (!cancelled) {
          setPage(result)
        }
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause.message)
          setPage(null)
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
  }, [filters, offset])

  useEffect(load, [load])

  // Al cambiar los filtros se vuelve a la primera página.
  function applyFilters(nextFilters) {
    setFilters(nextFilters)
    setOffset(0)
  }

  return (
    <section>
      <Filters
        categories={options.categories}
        brands={options.brands}
        onApply={applyFilters}
        disabled={loading}
      />

      {error ? <ErrorNotice message={error} onRetry={load} /> : null}
      {loading ? (
        <Loading title="Buscando productos...">Consultando el catálogo.</Loading>
      ) : null}

      {!loading && !error && page ? (
        <>
          {page.items.length === 0 ? (
            <Empty title="No hay productos que cumplan los filtros">
              Probá con otra categoría o ampliá el rango de precios.
            </Empty>
          ) : (
            <div className="grid">
              {page.items.map((product) => (
                <ProductCard key={product.product_id} product={product} onSelect={onSelect} />
              ))}
            </div>
          )}

          <Pagination
            total={page.total}
            limit={page.limit}
            offset={page.offset}
            hasMore={page.has_more}
            onChange={setOffset}
            disabled={loading}
          />
        </>
      ) : null}
    </section>
  )
}
