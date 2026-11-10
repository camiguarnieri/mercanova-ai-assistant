/**
 * Formateo de los valores del catálogo para mostrarlos.
 *
 * Acá vive la regla de los datos faltantes: si la API no trae un dato, se dice
 * que no está. Nunca se completa con un valor probable.
 */

/** Texto que muestra un dato que el catálogo no tiene cargado. */
export const MISSING = 'Sin dato'

/**
 * Lo que dice un campo de usos vacío.
 *
 * Lo escribe el backend, en MISSING_USES de backend/catalog_text.py: el
 * asistente recibe esa misma frase en el resultado de la herramienta, y acá se
 * reconoce para mostrarla con el estilo del campo vacío en vez de como un uso
 * más. Si cambia allá, cambia acá.
 */
export const MISSING_USES = 'el catálogo no lo aclara'

// Formatea un precio con su moneda, o avisa que no está cargado.
export function formatPrice(price, currency) {
  if (price === null || price === undefined) {
    return 'Precio no disponible'
  }
  return `${currency || ''} ${price.toFixed(2)}`.trim()
}

// Formatea el stock total disponible del producto.
export function formatStock(availableQty) {
  if (availableQty === null || availableQty === undefined) {
    return MISSING
  }
  if (availableQty === 0) {
    return 'Sin stock'
  }
  if (availableQty === 1) {
    return '1 unidad disponible'
  }
  return `${availableQty} unidades disponibles`
}

/**
 * Formatea el valor de una especificación.
 *
 * El texto 'None' es un valor real del catálogo y significa que el producto NO
 * tiene esa característica: se muestra como 'No'. Es distinto de que falte el
 * dato, que se muestra como 'Sin dato'.
 *
 * @param {object} specification La especificación tal como la devuelve la API.
 * @returns {string} El valor listo para mostrar.
 */
export function formatSpecification(specification) {
  const { value_text: valueText, value_number: valueNumber, unit } = specification
  if (valueText !== null && valueText !== undefined) {
    return valueText === 'None' ? 'No' : valueText
  }
  if (valueNumber !== null && valueNumber !== undefined) {
    return unit ? `${valueNumber} ${unit}` : `${valueNumber}`
  }
  return MISSING
}

/**
 * Formatea el momento en que se confirmó una orden.
 *
 * El backend lo manda en UTC y en ISO 8601; acá se muestra en la zona del
 * navegador, que es la del usuario. Si el valor no se puede leer se muestra
 * tal como vino: es mejor que inventar una fecha.
 *
 * @param {string} timestamp El `created_at` de la orden.
 * @returns {string} La fecha y la hora listas para mostrar.
 */
export function formatDateTime(timestamp) {
  if (!timestamp) {
    return MISSING
  }
  const moment = new Date(timestamp)
  if (Number.isNaN(moment.getTime())) {
    return timestamp
  }
  return moment.toLocaleString('es-UY', { dateStyle: 'medium', timeStyle: 'short' })
}

// Convierte una lista separada por punto y coma en elementos sueltos.
export function splitList(text) {
  if (!text) {
    return []
  }
  return text
    .split(';')
    .map((item) => item.trim())
    .filter(Boolean)
}

// Agrupa las especificaciones por attribute_group, conservando el orden.
export function groupSpecifications(specifications) {
  const groups = new Map()
  for (const specification of specifications) {
    const group = specification.attribute_group || MISSING
    if (!groups.has(group)) {
      groups.set(group, [])
    }
    groups.get(group).push(specification)
  }
  return [...groups.entries()].map(([group, items]) => ({ group, items }))
}
