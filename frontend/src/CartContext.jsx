/**
 * El carrito de la sesión, compartido por todas las vistas.
 *
 * Está en un contexto y no en props porque lo tocan tres lugares distintos: el
 * botón de cada tarjeta del catálogo, el panel del chat y la pestaña del
 * carrito. Es una pieza de React, no una dependencia nueva.
 *
 * El estado que vive acá es **una copia de lo que devolvió el servidor**, no
 * una cuenta propia: cada acción devuelve el carrito entero y reemplaza al
 * anterior. El frontend no suma totales ni descuenta stock por su cuenta.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import {
  addCartItem,
  fetchCart,
  removeCartItem,
  setCartItemQuantity,
} from './api/cart.js'
import { getSessionId } from './session.js'

/** El carrito vacío, para mostrar algo antes de la primera respuesta. */
const EMPTY_CART = { items: [], currency: null, total: 0, item_count: 0 }

const CartContext = createContext(null)

export function CartProvider({ children }) {
  // El identificador se crea una sola vez y es el mismo que usa el chat.
  const [sessionId] = useState(getSessionId)
  const [cart, setCart] = useState(EMPTY_CART)
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  // Corre una acción del carrito y guarda lo que devolvió el servidor.
  const run = useCallback(async (action) => {
    setPending(true)
    try {
      setCart(await action())
      setError(null)
      return { ok: true }
    } catch (cause) {
      // El mensaje del backend ya dice qué pasó y con qué número: se muestra
      // tal cual, no se reemplaza por uno genérico.
      setError(cause.message)
      return { ok: false, message: cause.message }
    } finally {
      setPending(false)
    }
  }, [])

  const refresh = useCallback(() => run(() => fetchCart(sessionId)), [run, sessionId])

  // El carrito se pide al arrancar: puede tener cosas de antes de la recarga.
  useEffect(() => {
    refresh()
  }, [refresh])

  const value = useMemo(
    () => ({
      sessionId,
      cart,
      error,
      pending,
      refresh,
      clearError: () => setError(null),
      addItem: (productId, quantity = 1) =>
        run(() => addCartItem(sessionId, productId, quantity)),
      setQuantity: (productId, quantity) =>
        run(() => setCartItemQuantity(sessionId, productId, quantity)),
      removeItem: (productId) => run(() => removeCartItem(sessionId, productId)),
      // La compra no se confirma desde acá: la hace la pantalla de
      // confirmación, que es la única que llama a checkout(). Después avisa
      // con esto para que el carrito vacío se refleje en todas las vistas.
      afterCheckout: refresh,
    }),
    [sessionId, cart, error, pending, refresh, run],
  )

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

/**
 * Devuelve el carrito de la sesión y las acciones para modificarlo.
 *
 * @returns {object} sessionId, cart, error, pending y las acciones.
 */
export function useCart() {
  const value = useContext(CartContext)
  if (value === null) {
    throw new Error('useCart() se usa dentro de <CartProvider>.')
  }
  return value
}
