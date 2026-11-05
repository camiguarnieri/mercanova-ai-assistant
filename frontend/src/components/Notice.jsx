/** Avisos de estado: cargando, error y sin resultados. */

// Panel común, para que los tres estados se vean igual que el resto.
function Panel({ variant, title, children, action }) {
  return (
    <div className={variant ? `notice notice-${variant}` : 'notice'} role={variant === 'error' ? 'alert' : 'status'}>
      {variant === 'loading' ? <span className="spinner" aria-hidden="true" /> : null}
      <p className="notice-title">{title}</p>
      {children ? <p className="notice-text">{children}</p> : null}
      {action}
    </div>
  )
}

// Muestra que se está esperando a la API.
export function Loading({ title = 'Cargando...', children }) {
  return (
    <Panel variant="loading" title={title}>
      {children}
    </Panel>
  )
}

// Muestra el error de la API con el mensaje que explica qué hacer.
export function ErrorNotice({ message, onRetry }) {
  return (
    <Panel
      variant="error"
      title="No se pudo cargar el catálogo"
      action={
        onRetry ? (
          <button type="button" className="button-secondary" onClick={onRetry}>
            Reintentar
          </button>
        ) : null
      }
    >
      {message}
    </Panel>
  )
}

// Muestra que la búsqueda no trajo resultados, en vez de una pantalla vacía.
export function Empty({ title = 'Sin resultados', children }) {
  return <Panel title={title}>{children}</Panel>
}
