/** Botón de micrófono del chat (RF-08): dicta y escribe el texto en el campo. */

import useSpeechRecognition, { SPEECH_MESSAGES } from '../useSpeechRecognition.js'

/** Ícono de micrófono, el mismo para los dos estados: lo que cambia es el color. */
function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        d="M12 15a3.5 3.5 0 0 0 3.5-3.5V6a3.5 3.5 0 0 0-7 0v5.5A3.5 3.5 0 0 0 12 15Z"
        fill="currentColor"
      />
      <path
        d="M18 11.5a6 6 0 0 1-12 0M12 17.5V21"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

/**
 * Dicta una consulta y la deja escrita en el campo de texto. `onTranscript`
 * recibe el texto; el envío lo sigue haciendo el usuario con el botón Enviar.
 */
export default function VoiceInput({ onTranscript, disabled = false }) {
  const { supported, listening, error, start, stop } = useSpeechRecognition({
    onResult: onTranscript,
  })

  // Sin la API no hay nada que intentar: el botón queda deshabilitado y al lado
  // se explica qué navegador hace falta.
  if (!supported) {
    return (
      <>
        <button
          type="button"
          className="mic-button"
          disabled
          aria-label="Dictar la consulta (no disponible en este navegador)"
          title={SPEECH_MESSAGES.unsupported}
        >
          <MicIcon />
        </button>
        <p className="mic-status" role="status">
          {SPEECH_MESSAGES.unsupported}
        </p>
      </>
    )
  }

  return (
    <>
      <button
        type="button"
        className={listening ? 'mic-button mic-button-listening' : 'mic-button'}
        onClick={listening ? stop : start}
        disabled={disabled}
        aria-pressed={listening}
        aria-label={listening ? 'Dejar de escuchar' : 'Dictar la consulta'}
      >
        <MicIcon />
      </button>

      {listening ? (
        <p className="mic-status mic-status-listening" role="status">
          <span className="mic-pulse" aria-hidden="true" />
          Escuchando... hablá y después revisá el texto antes de enviarlo.
        </p>
      ) : null}

      {!listening && error ? (
        <p className="mic-status mic-status-error" role="alert">
          {error}
        </p>
      ) : null}
    </>
  )
}
