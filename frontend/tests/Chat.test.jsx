/**
 * Tests de la pantalla de chat con entrada por voz: lo dictado se escribe en el
 * campo y no se manda solo. El envío sigue siendo del usuario.
 */

import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  installSpeechRecognition,
  lastRecognition,
  removeSpeechRecognition,
} from './speechMock.js'

// El chat no habla con la API en estos tests: lo que se prueba es la entrada.
const sendChatMessage = vi.fn()
vi.mock('../src/api/client.js', () => ({
  sendChatMessage: (...args) => sendChatMessage(...args),
}))

// El carrito tampoco: se reemplaza el contexto por uno vacío y quieto.
vi.mock('../src/CartContext.jsx', () => ({
  useCart: () => ({
    sessionId: 'sesion-de-test',
    cart: { session_id: 'sesion-de-test', items: [], total: 0 },
    error: null,
    pending: false,
    refresh: () => {},
    clearError: () => {},
  }),
}))

const { default: Chat } = await import('../src/pages/Chat.jsx')

// El campo donde el usuario escribe su consulta.
function input() {
  return screen.getByLabelText('Mensaje para el asistente')
}

// Apretar el micrófono.
function clickMic() {
  act(() => {
    screen.getByRole('button', { name: /dictar la consulta/i }).click()
  })
}

// Escribir a mano en el campo, como lo haría el usuario.
function type(text) {
  fireEvent.change(input(), { target: { value: text } })
}

// Apretar Enviar y esperar a que la respuesta de la API se haya procesado.
async function clickSend() {
  await act(async () => {
    screen.getByRole('button', { name: /^Enviar/ }).click()
  })
}

describe('Chat con entrada por voz', () => {
  beforeEach(() => {
    sendChatMessage.mockReset()
    sendChatMessage.mockResolvedValue({ reply: 'Hola', products: [], tools_used: [] })
    installSpeechRecognition()
  })

  afterEach(() => {
    removeSpeechRecognition()
  })

  it('escribe lo dictado en el campo de texto', () => {
    render(<Chat onGoToCart={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitResult('necesito una notebook para programar')
      lastRecognition().emitEnd()
    })

    expect(input()).toHaveValue('necesito una notebook para programar')
  })

  it('no manda el mensaje solo: el envío lo sigue haciendo el usuario', async () => {
    render(<Chat onGoToCart={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitResult('necesito una notebook para programar')
      lastRecognition().emitEnd()
    })

    // Lo dictado quedó en el campo y la API no se llamó.
    expect(sendChatMessage).not.toHaveBeenCalled()
    expect(screen.queryByText('necesito una notebook para programar')).toBeNull()

    // Recién cuando el usuario aprieta Enviar, sale.
    await clickSend()
    expect(sendChatMessage).toHaveBeenCalledWith(
      'sesion-de-test',
      'necesito una notebook para programar',
    )
  })

  it('el botón de enviar queda habilitado con el texto dictado', () => {
    render(<Chat onGoToCart={() => {}} />)
    expect(screen.getByRole('button', { name: /^Enviar/ })).toBeDisabled()

    clickMic()
    act(() => {
      lastRecognition().emitResult('auriculares hasta 200 dólares')
      lastRecognition().emitEnd()
    })

    expect(screen.getByRole('button', { name: /^Enviar/ })).not.toBeDisabled()
  })

  it('agrega lo dictado al final de lo que ya estaba escrito', () => {
    render(<Chat onGoToCart={() => {}} />)
    type('auriculares')

    clickMic()
    act(() => {
      lastRecognition().emitResult('para viajar')
      lastRecognition().emitEnd()
    })

    expect(input()).toHaveValue('auriculares para viajar')
  })

  it('un error de voz no mete nada en la conversación ni en el campo', () => {
    render(<Chat onGoToCart={() => {}} />)
    clickMic()

    act(() => {
      lastRecognition().emitError('not-allowed')
      lastRecognition().emitEnd()
    })

    expect(input()).toHaveValue('')
    expect(sendChatMessage).not.toHaveBeenCalled()
    // El aviso es del micrófono, no un mensaje del asistente.
    expect(screen.getByText(/habilitalo para este sitio/i)).toBeInTheDocument()
  })
})

describe('Chat en un navegador sin Web Speech API', () => {
  beforeEach(() => {
    sendChatMessage.mockReset()
    sendChatMessage.mockResolvedValue({ reply: 'Hola', products: [], tools_used: [] })
    removeSpeechRecognition()
  })

  it('deja escribir y enviar igual, con el micrófono deshabilitado', async () => {
    render(<Chat onGoToCart={() => {}} />)

    expect(screen.getByRole('button', { name: /no disponible en este navegador/i })).toBeDisabled()
    expect(screen.getByText(/Chrome o Edge/)).toBeInTheDocument()

    type('auriculares')
    await clickSend()

    expect(sendChatMessage).toHaveBeenCalledWith('sesion-de-test', 'auriculares')
  })
})
