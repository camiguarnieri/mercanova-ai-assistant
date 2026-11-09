/**
 * Las herramientas que el asistente usó para armar una respuesta.
 *
 * Es la evidencia visible de que los datos salen del catálogo y no del modelo
 * (RF-18): se muestra debajo de cada respuesta, plegada y en letra chica.
 */

/** Qué hizo cada herramienta, en español, para que se entienda sin leer el nombre. */
const LABELS = {
  search_products: 'Consultó el catálogo',
  get_product_details: 'Pidió la ficha del producto',
  check_availability: 'Consultó el stock',
  compare_products: 'Comparó productos',
  get_related_products: 'Buscó productos relacionados',
  // No es una herramienta del modelo: la corre el sistema antes del turno, y
  // por eso se nombra distinto.
  lookup_product_name: 'El sistema buscó en el catálogo el nombre que escribiste',
}

// Escribe un valor como se escribiría en una llamada: texto entre comillas.
function formatValue(value) {
  if (Array.isArray(value)) {
    return `[${value.map(formatValue).join(', ')}]`
  }
  if (typeof value === 'string') {
    return `'${value}'`
  }
  return String(value)
}

// Arma la lista de argumentos, salteando los que llegaron vacíos.
function formatArguments(args) {
  return Object.entries(args || {})
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([name, value]) => `${name}=${formatValue(value)}`)
    .join(', ')
}

// Arma la línea de una invocación: qué hizo y con qué argumentos.
function describe(tool) {
  const label = LABELS[tool.name] || 'Usó una herramienta'
  return `${label}: ${tool.name}(${formatArguments(tool.arguments)})`
}

// Deja solo las invocaciones que se pueden mostrar.
function named(tools) {
  // El modelo puede pedir una herramienta sin nombre: no es una consulta al
  // catálogo, así que no se muestra en vez de dejar una viñeta vacía.
  return (tools || []).filter((tool) => tool && typeof tool.name === 'string' && tool.name.trim())
}

export default function ToolTrace({ tools }) {
  const invocations = named(tools)
  if (invocations.length === 0) {
    return <p className="tool-trace-empty">No consultó el catálogo en esta respuesta.</p>
  }

  const count = invocations.length
  return (
    <details className="tool-trace">
      <summary>
        {count === 1 ? 'Consultó 1 herramienta del catálogo' : `Consultó ${count} herramientas del catálogo`}
      </summary>
      <ul className="tool-trace-list">
        {invocations.map((tool, index) => (
          <li key={`${tool.name}-${index}`}>
            <code>{describe(tool)}</code>
          </li>
        ))}
      </ul>
    </details>
  )
}
