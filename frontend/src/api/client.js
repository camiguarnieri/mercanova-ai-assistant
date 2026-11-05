/**
 * Acceso a la API del catálogo.
 *
 * Todo lo que muestra la interfaz sale de acá: el frontend no inventa precios
 * ni stock, y si la API no devuelve un dato se muestra como faltante.
 */

// URL base de la API, de la variable de entorno de Vite, con default seguro.
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/** Error de la capa de acceso a la API, con un mensaje accionable. */
export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Saca los parámetros vacíos, para no mandar filtros que el usuario no puso.
function cleanParams(params) {
  const entries = Object.entries(params).filter(
    ([, value]) => value !== null && value !== undefined && value !== '',
  )
  return new URLSearchParams(entries)
}

// Pide un recurso a la API y traduce los errores a mensajes en español.
async function request(path, params = {}) {
  const query = cleanParams(params).toString()
  const url = `${API_URL}${path}${query ? `?${query}` : ''}`

  let response
  try {
    response = await fetch(url)
  } catch (cause) {
    throw new ApiError(
      `No se pudo conectar con la API en ${API_URL}. Verificá que esté corriendo: ` +
        'uvicorn backend.api:app --reload',
      0,
    )
  }

  if (!response.ok) {
    const detail = await readDetail(response)
    throw new ApiError(detail, response.status)
  }
  return response.json()
}

// Lee el campo detail que manda la API, o arma un mensaje según el estado.
async function readDetail(response) {
  try {
    const body = await response.json()
    if (body && body.detail) {
      return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    }
  } catch {
    // La respuesta no era JSON: se usa el mensaje por estado.
  }
  if (response.status === 404) {
    return 'No se encontró lo que buscabas en el catálogo.'
  }
  if (response.status === 503) {
    return 'La base del catálogo no está disponible. Corré: python scripts/load_dataset.py'
  }
  return `La API respondió con un error ${response.status}.`
}

/**
 * Busca productos en el catálogo.
 *
 * @param {object} filters Filtros y paginado: category, brand, min_price,
 *   max_price, search, limit y offset.
 * @returns {Promise<object>} La página con items, total, limit, offset y has_more.
 */
export function fetchProducts(filters) {
  return request('/products', filters)
}

/**
 * Trae la ficha completa de un producto.
 *
 * @param {string} productId Identificador del producto.
 * @returns {Promise<object>} El detalle, con precio, stock y especificaciones.
 */
export function fetchProduct(productId) {
  return request(`/products/${encodeURIComponent(productId)}`)
}

/**
 * Lista los pares categoría/subcategoría del catálogo.
 *
 * @returns {Promise<Array<object>>} Las categorías.
 */
export function fetchCategories() {
  return request('/categories')
}

/**
 * Lista las marcas del catálogo.
 *
 * @returns {Promise<Array<object>>} Las marcas.
 */
export function fetchBrands() {
  return request('/brands')
}
