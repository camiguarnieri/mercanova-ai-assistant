/** Tests del botón de micrófono: estados, resultado y los cuatro casos límite. */

import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import VoiceInput from '../src/components/VoiceInput.jsx'
import { SPEECH_MESSAGES } from '../src/useSpeechRecognition.js'
import {
  installSpeechRecognition,
  lastRecognition,
  removeSpeechRecognition,
} from './speechMock.js'

// Apretar el micrófono. Va envuelto en act() porque el click cambia estado.
function clickMic() {
  act(() => {
    screen.getByRole('button', { name: /dictar la consulta/i }).click()
  })
}

describe('VoiceInput con la Web Speech API disponible', () => {
  beforeEach(() => {
    installSpeechRecognition()
  })

  afterEach(() => {
    removeSpeechRecognition()
  })

  it('arranca con el botón habilitado y sin estado de escucha', () => {
    render(<VoiceInput onTranscript={() => {}} />)

    const button = screen.getByRole('button', { name: 'Dictar la consulta' })
    expect(button).not.toBeDisabled()
    expect(button.getAttribute('aria-pressed')).toBe('false')
    expect(screen.queryByText(/escuchando/i)).toBeNull()
  })

  it('configura el reconocimiento en español y sin resultados parciales', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    const recognition = lastRecognition()
    expect(recognition.lang).toBe('es-UY')
    expect(recognition.continuous).toBe(false)
    expect(recognition.interimResults).toBe(false)
    expect(recognition.maxAlternatives).toBe(1)
    expect(recognition.started).toBe(1)
  })

  it('muestra que está escuchando mientras el micrófono está abierto', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    expect(screen.getByRole('status')).toHaveTextContent(/escuchando/i)
    const button = screen.getByRole('button', { name: 'Dejar de escuchar' })
    expect(button.getAttribute('aria-pressed')).toBe('true')
    expect(button.className).toContain('mic-button-listening')
  })

  it('al apretarlo mientras escucha, corta el reconocimiento', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    act(() => {
      screen.getByRole('button', { name: 'Dejar de escuchar' }).click()
    })

    expect(lastRecognition().stopped).toBe(1)
  })

  it('entrega el texto transcripto y vuelve al estado inicial', () => {
    const onTranscript = vi.fn()
    render(<VoiceInput onTranscript={onTranscript} />)
    clickMic()

    act(() => {
      lastRecognition().emitResult('  necesito auriculares para viajar  ')
      lastRecognition().emitEnd()
    })

    expect(onTranscript).toHaveBeenCalledTimes(1)
    expect(onTranscript).toHaveBeenCalledWith('necesito auriculares para viajar')
    expect(screen.queryByText(/escuchando/i)).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('button', { name: 'Dictar la consulta' })).not.toBeDisabled()
  })

  it('no entrega nada si el evento viene sin texto', () => {
    const onTranscript = vi.fn()
    render(<VoiceInput onTranscript={onTranscript} />)
    clickMic()

    act(() => {
      lastRecognition().onresult({ results: [] })
      lastRecognition().emitEnd()
    })

    expect(onTranscript).not.toHaveBeenCalled()
  })

  it('queda deshabilitado mientras se está mandando un mensaje', () => {
    render(<VoiceInput onTranscript={() => {}} disabled />)

    expect(screen.getByRole('button', { name: 'Dictar la consulta' })).toBeDisabled()
  })

  // Caso límite 2: el usuario no da permiso de micrófono.
  it('explica cómo habilitar el micrófono si se negó el permiso', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitError('not-allowed')
      lastRecognition().emitEnd()
    })

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(SPEECH_MESSAGES['not-allowed'])
    expect(alert.textContent).toMatch(/permiso/i)
    expect(screen.queryByText(/escuchando/i)).toBeNull()
  })

  // Caso límite 3: silencio o nada reconocible.
  it('avisa que no se escuchó nada cuando el navegador informa silencio', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitError('no-speech')
      lastRecognition().emitEnd()
    })

    expect(screen.getByRole('alert')).toHaveTextContent('No te escuché.')
  })

  // Caso límite 3, variante: termina sin texto y sin error. Para el usuario es
  // lo mismo que el silencio, así que recibe el mismo mensaje.
  it('avisa que no se escuchó nada cuando termina sin texto ni error', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitEnd()
    })

    expect(screen.getByRole('alert')).toHaveTextContent('No te escuché.')
  })

  // Caso límite 4: el reconocimiento depende de un servicio externo.
  it('avisa que no se pudo conectar ante un error de red', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitError('network')
      lastRecognition().emitEnd()
    })

    expect(screen.getByRole('alert')).toHaveTextContent(SPEECH_MESSAGES.network)
    expect(screen.getByRole('alert').textContent).toMatch(/conectar/i)
  })

  it('avisa que hace falta HTTPS si el navegador bloquea el servicio', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitError('service-not-allowed')
      lastRecognition().emitEnd()
    })

    expect(screen.getByRole('alert').textContent).toMatch(/HTTPS|localhost/)
  })

  it('no muestra error si la cancelación fue del propio usuario', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitResult('auriculares')
      lastRecognition().emitError('aborted')
      lastRecognition().emitEnd()
    })

    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('traduce un código desconocido a un mensaje accionable, no técnico', () => {
    render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitError('algo-que-no-conocemos')
      lastRecognition().emitEnd()
    })

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(SPEECH_MESSAGES.default)
    expect(alert.textContent).not.toMatch(/algo-que-no-conocemos/)
  })

  it('el error de un intento no queda pegado al siguiente', () => {
    const onTranscript = vi.fn()
    render(<VoiceInput onTranscript={onTranscript} />)
    clickMic()
    act(() => {
      lastRecognition().emitError('no-speech')
      lastRecognition().emitEnd()
    })
    expect(screen.getByRole('alert')).toBeInTheDocument()

    clickMic()

    expect(screen.queryByRole('alert')).toBeNull()
    act(() => {
      lastRecognition().emitResult('auriculares')
      lastRecognition().emitEnd()
    })
    expect(onTranscript).toHaveBeenCalledWith('auriculares')
  })

  it('corta el reconocimiento si la pantalla se desmonta mientras escucha', () => {
    const view = render(<VoiceInput onTranscript={() => {}} />)
    clickMic()

    view.unmount()

    expect(lastRecognition().aborted).toBe(1)
  })
})

// Caso límite 1: el navegador no tiene la Web Speech API, por ejemplo Firefox.
describe('VoiceInput sin la Web Speech API', () => {
  beforeEach(() => {
    removeSpeechRecognition()
  })

  it('deshabilita el botón y dice qué navegador hace falta', () => {
    render(<VoiceInput onTranscript={() => {}} />)

    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button.getAttribute('title')).toMatch(/Chrome o Edge/)
    expect(screen.getByRole('status')).toHaveTextContent(/Chrome o Edge/)
  })

  it('no crea ningún reconocimiento', () => {
    render(<VoiceInput onTranscript={() => {}} />)

    expect(lastRecognition()).toBeUndefined()
  })
})
