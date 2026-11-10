/**
 * Acceso a la API del catálogo y del chat.
 *
 * Todo lo que muestra la interfaz sale de acá: el frontend no inventa precios
 * ni stock, y si la API no devuelve un dato se muestra como faltante.
 *
 * Cómo se habla con la API está en `http.js`; el carrito y las órdenes, en
 * `cart.js`. Se reexportan `API_URL` y `ApiError` porque son parte del
 * contrato que ya usan las vistas.
 */

import { API_URL, ApiError, post, request } from './http.js'

export { API_URL, ApiError }

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

/**
 * Manda un mensaje al asistente y trae su respuesta.
 *
 * El historial lo guarda el servidor: acá solo viaja el mensaje nuevo y la
 * sesión a la que pertenece.
 *
 * @param {string} sessionId Identificador de la conversación.
 * @param {string} message Lo que escribió el usuario.
 * @returns {Promise<object>} La respuesta con session_id, reply y tools_used.
 */
export function sendChatMessage(sessionId, message) {
  return post('/chat', { session_id: sessionId, message })
}
