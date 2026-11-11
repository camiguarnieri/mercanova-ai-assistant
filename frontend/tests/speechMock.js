/**
 * Doble de la Web Speech API para los tests.
 *
 * jsdom no trae `SpeechRecognition`, así que no hay nada que espiar: se instala
 * este doble en `window` y cada caso dispara a mano los eventos que el navegador
 * dispararía. Lo que se verifica es con qué se configuró el reconocimiento y qué
 * hace la interfaz ante cada evento, no el reconocimiento en sí.
 */

/** Instancias creadas, en orden. La última es la del caso en curso. */
export const instances = []

/** Reemplazo de `SpeechRecognition`: guarda la configuración y los handlers. */
export class FakeSpeechRecognition {
  constructor() {
    this.lang = null
    this.continuous = null
    this.interimResults = null
    this.maxAlternatives = null
    this.onresult = null
    this.onerror = null
    this.onend = null
    this.started = 0
    this.stopped = 0
    this.aborted = 0
    instances.push(this)
  }

  start() {
    this.started += 1
  }

  stop() {
    this.stopped += 1
  }

  abort() {
    this.aborted += 1
  }

  // Lo que dispara el navegador cuando transcribió algo.
  emitResult(transcript) {
    this.onresult?.({ results: [[{ transcript }]] })
  }

  // Lo que dispara el navegador cuando algo falló: 'not-allowed', 'no-speech',
  // 'network', 'service-not-allowed', 'aborted'.
  emitError(code) {
    this.onerror?.({ error: code })
  }

  // Lo que dispara el navegador al cerrar el micrófono, pase lo que pase.
  emitEnd() {
    this.onend?.()
  }
}

/** La última instancia creada, que es la que el componente está usando. */
export function lastRecognition() {
  return instances[instances.length - 1]
}

// Instala el doble en window, como lo expone Chrome con el prefijo.
export function installSpeechRecognition() {
  instances.length = 0
  window.webkitSpeechRecognition = FakeSpeechRecognition
  return FakeSpeechRecognition
}

// Deja a window sin la API, como Firefox.
export function removeSpeechRecognition() {
  instances.length = 0
  delete window.SpeechRecognition
  delete window.webkitSpeechRecognition
}
