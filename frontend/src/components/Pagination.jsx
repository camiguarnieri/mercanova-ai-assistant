/** Paginación del listado, con limit, offset y has_more de la API. */

// Muestra en qué tramo del total se está y permite moverse de página.
export default function Pagination({ total, limit, offset, hasMore, onChange, disabled }) {
  const first = total === 0 ? 0 : offset + 1
  const last = offset + limit < total ? offset + limit : total
  const page = Math.floor(offset / limit) + 1
  const pages = Math.max(1, Math.ceil(total / limit))

  return (
    <nav className="pagination">
      <button
        type="button"
        onClick={() => onChange(Math.max(0, offset - limit))}
        disabled={disabled || offset === 0}
      >
        Anterior
      </button>

      <span className="pagination-status">
        {first}–{last} de {total} · página {page} de {pages}
      </span>

      <button
        type="button"
        onClick={() => onChange(offset + limit)}
        disabled={disabled || !hasMore}
      >
        Siguiente
      </button>
    </nav>
  )
}
