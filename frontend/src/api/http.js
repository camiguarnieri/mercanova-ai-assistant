/**
 * Acceso HTTP a la API: la URL base, los verbos y la traducción de errores.
 *
 * Acá no se sabe qué recursos existen: eso está en `client.js` (catálogo y
 * chat) y en `cart.js` (carrito y órdenes). Lo único que vive acá es cómo se
 * habla con la API y cómo se convierte una respuesta con error en un mensaje
 * que el usuario pueda accionar.
 */

/** URL base de la API, de la variable de entorno de Vite, con default seguro. */
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

// Arma la URL completa de un recurso con sus parámetros de consulta.
function urlOf(path, params) {
  const query = cleanParams(params).toString()
  return `${API_URL}${path}${query ? `?${query}` : ''}`
}

// Llama a la API y traduce los errores a mensajes en español.
async function send(url, options) {
  let response
  try {
    response = await fetch(url, options)
  } catch {
    throw new ApiError(
      `No se pudo conectar con la API en ${API_URL}. Verificá que esté corriendo: ` +
        'uvicorn backend.api:app --reload',
      0,
    )
  }

  if (!response.ok) {
    throw new ApiError(await readDetail(response), response.status)
  }
  return response.json()
}

/**
 * Pide un recurso a la API.
 *
 * @param {string} path Ruta del recurso, por ejemplo '/products'.
 * @param {object} params Parámetros de consulta; los vacíos no se mandan.
 * @returns {Promise<object>} El cuerpo de la respuesta.
 */
export function request(path, params = {}) {
  return send(urlOf(path, params))
}

// Manda un cuerpo JSON con el verbo que corresponda.
function withBody(method) {
  return (path, body) =>
    send(`${API_URL}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
}

/** Crea un recurso o manda una acción. */
export const post = withBody('POST')

/** Reemplaza un recurso, como la cantidad de una línea del carrito. */
export const put = withBody('PUT')

/**
 * Borra un recurso.
 *
 * @param {string} path Ruta del recurso.
 * @param {object} params Parámetros de consulta.
 * @returns {Promise<object>} El cuerpo de la respuesta.
 */
export function remove(path, params = {}) {
  return send(urlOf(path, params), { method: 'DELETE' })
}

// Lee el campo detail que manda la API, o arma un mensaje según el estado.
async function readDetail(response) {
  try {
    const body = await response.json()
    if (body && body.detail) {
      return detailText(body.detail)
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

// Convierte el detail en una línea de texto, venga como venga.
function detailText(detail) {
  if (typeof detail === 'string') {
    return detail
  }
  // FastAPI rechaza un cuerpo mal armado con una lista de errores por campo;
  // se arma una frase con los mensajes en vez de mostrar el JSON crudo.
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item.msg).filter(Boolean)
    if (messages.length > 0) {
      return messages.join('. ')
    }
  }
  return JSON.stringify(detail)
}
