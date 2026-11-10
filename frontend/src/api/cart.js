/**
 * Acceso a la API del carrito, del checkout y de las órdenes.
 *
 * El carrito no se guarda en el navegador: vive en el servidor, atado al
 * `session_id`, y acá solo se lo pide y se lo modifica. El total y los precios
 * que muestra la pantalla vienen de estas respuestas, nunca de una suma hecha
 * en el cliente.
 *
 * El `session_id` es el mismo que usa el chat (`session.js`), así el carrito
 * que escribe el asistente es el que ve el usuario.
 */

import { post, put, remove, request } from './http.js'

/**
 * Trae el carrito de una sesión, con los precios del catálogo de ahora.
 *
 * @param {string} sessionId Identificador de la sesión.
 * @returns {Promise<object>} El carrito con items, currency, total e item_count.
 */
export function fetchCart(sessionId) {
  return request('/cart', { session_id: sessionId })
}

/**
 * Agrega unidades de un producto al carrito.
 *
 * El stock lo valida el backend: si no alcanza, el pedido falla con un
 * mensaje que dice cuántas unidades hay.
 *
 * @param {string} sessionId Identificador de la sesión.
 * @param {string} productId Identificador del producto.
 * @param {number} quantity Unidades a sumar a las que ya haya.
 * @returns {Promise<object>} El carrito después de agregar.
 */
export function addCartItem(sessionId, productId, quantity = 1) {
  return post('/cart/items', {
    session_id: sessionId,
    product_id: productId,
    quantity,
  })
}

/**
 * Deja la línea de un producto en una cantidad exacta.
 *
 * @param {string} sessionId Identificador de la sesión.
 * @param {string} productId Identificador del producto.
 * @param {number} quantity Cantidad final de la línea, mayor a 0.
 * @returns {Promise<object>} El carrito después del cambio.
 */
export function setCartItemQuantity(sessionId, productId, quantity) {
  return put(`/cart/items/${encodeURIComponent(productId)}`, {
    session_id: sessionId,
    quantity,
  })
}

/**
 * Saca un producto del carrito, con todas sus unidades.
 *
 * @param {string} sessionId Identificador de la sesión.
 * @param {string} productId Identificador del producto.
 * @returns {Promise<object>} El carrito después de sacarlo.
 */
export function removeCartItem(sessionId, productId) {
  return remove(`/cart/items/${encodeURIComponent(productId)}`, {
    session_id: sessionId,
  })
}

/**
 * Confirma la compra y crea la orden.
 *
 * `confirmed` va en true porque esta función se llama desde la pantalla de
 * confirmación y desde ningún otro lado: el backend rechaza el pedido sin esa
 * marca, así que la pantalla no se puede saltear ni desde la consola.
 *
 * @param {string} sessionId Identificador de la sesión.
 * @param {object} shipping Datos de envío: customerName y shippingAddress.
 * @returns {Promise<object>} La orden creada, con su order_id y su total.
 */
export function checkout(sessionId, { customerName, shippingAddress }) {
  return post('/checkout', {
    session_id: sessionId,
    customer_name: customerName,
    shipping_address: shippingAddress,
    confirmed: true,
  })
}

/**
 * Lista las órdenes de una sesión, la más nueva primero.
 *
 * @param {string} sessionId Identificador de la sesión.
 * @returns {Promise<Array<object>>} Las órdenes con sus líneas.
 */
export function fetchOrders(sessionId) {
  return request('/orders', { session_id: sessionId })
}
