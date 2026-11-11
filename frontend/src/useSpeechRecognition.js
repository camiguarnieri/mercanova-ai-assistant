/**
 * Entrada por voz (RF-08): envuelve la Web Speech API del navegador y la expone
 * como un hook con tres cosas: si se puede usar, si está escuchando y qué salió
 * mal. El audio lo transcribe el navegador; acá no hay nada que vaya al backend.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/** Idioma de reconocimiento por defecto: español de Uruguay. */
export const DEFAULT_LANG = 'es-UY'

/**
 * Mensajes por código de error de la Web Speech API. Son los que ve el usuario,
 * así que cada uno dice qué hacer, no qué falló.
 */
export const SPEECH_MESSAGES = {
  unsupported:
    'Este navegador no reconoce voz. Para dictar tu consulta usá Chrome o Edge; mientras tanto, escribila.',
  'not-allowed':
    'No tenemos permiso para usar el micrófono. Habilitalo para este sitio desde el ícono de la barra de direcciones y probá de nuevo.',
  'service-not-allowed':
    'El navegador bloqueó el reconocimiento de voz. Solo funciona sobre HTTPS o en localhost.',
  'no-speech': 'No te escuché. Apretá el micrófono y probá de nuevo.',
  'audio-capture':
    'No encontramos un micrófono conectado. Conectá uno, dale permiso y probá de nuevo.',
  network:
    'No se pudo conectar con el servicio de reconocimiento de voz. Revisá tu conexión y probá de nuevo.',
  default: 'No se pudo usar la entrada por voz. Probá de nuevo o escribí el mensaje.',
}

// Devuelve el constructor de reconocimiento del navegador, o null si no existe.
export function getSpeechRecognition() {
  if (typeof window === 'undefined') {
    return null
  }
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

// Traduce un código de error de la API al mensaje que se le muestra al usuario.
function messageFor(code) {
  return SPEECH_MESSAGES[code] || SPEECH_MESSAGES.default
}

// Saca el texto transcripto del evento, o '' si el evento no trajo ninguno.
function transcriptOf(event) {
  const alternatives = event?.results?.[0]
  const text = alternatives?.[0]?.transcript
  return typeof text === 'string' ? text.trim() : ''
}

/**
 * Hook de dictado. `onResult` recibe el texto transcripto; el hook no lo manda
 * a ningún lado, de eso se encarga quien lo usa.
 */
export default function useSpeechRecognition({ lang = DEFAULT_LANG, onResult } = {}) {
  // Se resuelve una sola vez: el navegador no cambia en el medio de la sesión.
  const [supported] = useState(() => getSpeechRecognition() !== null)
  const [listening, setListening] = useState(false)
  const [error, setError] = useState(null)
  const recognitionRef = useRef(null)
  // Para saber, cuando termina, si llegó a haber un resultado o un error.
  const outcomeRef = useRef({ result: false, error: false })
  // El callback puede cambiar en cada render; el que vale es el último.
  const onResultRef = useRef(onResult)

  useEffect(() => {
    onResultRef.current = onResult
  }, [onResult])

  // Corta el reconocimiento si el componente se va mientras escucha.
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort?.()
      recognitionRef.current = null
    }
  }, [])

  // Borra el último mensaje de error.
  const clearError = useCallback(() => setError(null), [])

  // Arranca a escuchar. Si el navegador no soporta la API, solo avisa.
  const start = useCallback(() => {
    setError(null)
    const Recognition = getSpeechRecognition()
    if (!Recognition) {
      setError(SPEECH_MESSAGES.unsupported)
      return
    }
    if (recognitionRef.current) {
      return
    }

    let recognition
    try {
      recognition = new Recognition()
    } catch {
      setError(SPEECH_MESSAGES.default)
      return
    }

    recognition.lang = lang
    recognition.continuous = false
    recognition.interimResults = false
    recognition.maxAlternatives = 1
    outcomeRef.current = { result: false, error: false }

    recognition.onresult = (event) => {
      const text = transcriptOf(event)
      if (!text) {
        return
      }
      outcomeRef.current.result = true
      onResultRef.current?.(text)
    }

    recognition.onerror = (event) => {
      // 'aborted' es la cancelación del propio usuario: no es un error que mostrar.
      if (event?.error === 'aborted') {
        return
      }
      outcomeRef.current.error = true
      setError(messageFor(event?.error))
    }

    recognition.onend = () => {
      recognitionRef.current = null
      setListening(false)
      // Terminó sin texto y sin error: el navegador no avisó nada, pero para el
      // usuario el caso es el mismo que el silencio.
      if (!outcomeRef.current.result && !outcomeRef.current.error) {
        setError(SPEECH_MESSAGES['no-speech'])
      }
    }

    recognitionRef.current = recognition
    setListening(true)
    try {
      recognition.start()
    } catch {
      recognitionRef.current = null
      setListening(false)
      setError(SPEECH_MESSAGES.default)
    }
  }, [lang])

  // Deja de escuchar y procesa lo que se haya dicho hasta ahora.
  const stop = useCallback(() => {
    recognitionRef.current?.stop?.()
  }, [])

  return { supported, listening, error, start, stop, clearError }
}
