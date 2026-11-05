/** Formulario de filtros del listado. */

import { useState } from 'react'

/** Filtros vacíos, que equivalen a no filtrar nada. */
export const EMPTY_FILTERS = {
  search: '',
  category: '',
  brand: '',
  min_price: '',
  max_price: '',
}

// Deja elegir categoría, marca, rango de precio y texto libre.
export default function Filters({ categories, brands, onApply, disabled }) {
  const [draft, setDraft] = useState(EMPTY_FILTERS)

  // Las categorías vienen por par categoría/subcategoría: acá se muestra la
  // categoría una sola vez.
  const categoryNames = [...new Set(categories.map((item) => item.category_name))].sort()

  function update(field, value) {
    setDraft((current) => ({ ...current, [field]: value }))
  }

  function submit(event) {
    event.preventDefault()
    onApply(draft)
  }

  function clear() {
    setDraft(EMPTY_FILTERS)
    onApply(EMPTY_FILTERS)
  }

  return (
    <form className="filters" onSubmit={submit}>
      <label className="filters-search">
        Buscar
        <input
          type="search"
          value={draft.search}
          placeholder="monitor, gaming, office work"
          onChange={(event) => update('search', event.target.value)}
        />
      </label>

      <label>
        Categoría
        <select
          value={draft.category}
          onChange={(event) => update('category', event.target.value)}
        >
          <option value="">Todas</option>
          {categoryNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      <label>
        Marca
        <select value={draft.brand} onChange={(event) => update('brand', event.target.value)}>
          <option value="">Todas</option>
          {brands.map((brand) => (
            <option key={brand.brand_id} value={brand.brand_name}>
              {brand.brand_name}
            </option>
          ))}
        </select>
      </label>

      <label>
        Precio mínimo
        <input
          type="number"
          min="0"
          step="0.01"
          value={draft.min_price}
          onChange={(event) => update('min_price', event.target.value)}
        />
      </label>

      <label>
        Precio máximo
        <input
          type="number"
          min="0"
          step="0.01"
          value={draft.max_price}
          onChange={(event) => update('max_price', event.target.value)}
        />
      </label>

      <div className="filters-actions">
        <button type="submit" disabled={disabled}>
          Aplicar
        </button>
        <button type="button" className="button-secondary" onClick={clear} disabled={disabled}>
          Limpiar
        </button>
      </div>
    </form>
  )
}
