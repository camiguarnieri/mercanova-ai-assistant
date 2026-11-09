/**
 * Identificador de la conversación con el asistente.
 *
 * Se genera en el cliente la primera vez y se guarda en el navegador, así el
 * usuario sigue la misma conversación si recarga la página. El historial en sí
 * lo guarda el servidor: acá solo vive la clave con la que se lo pide.
 */

/** Clave con la que se guarda el identificador en el navegador. */
export const SESSION_KEY = 'mercanova.session_id'

// Arma un identificador nuevo, con crypto si el navegador lo tiene.
function createSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // Fallback para navegadores sin randomUUID: alcanza para distinguir pestañas.
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/**
 * Devuelve el identificador de la sesión, creándolo si es la primera vez.
 *
 * Si el navegador tiene el almacenamiento bloqueado, devuelve uno nuevo sin
 * guardarlo: la conversación funciona igual, solo no sobrevive a una recarga.
 *
 * @returns {string} El identificador de la conversación.
 */
export function getSessionId() {
  try {
    const saved = localStorage.getItem(SESSION_KEY)
    if (saved) {
      return saved
    }
    const created = createSessionId()
    localStorage.setItem(SESSION_KEY, created)
    return created
  } catch {
    return createSessionId()
  }
}
