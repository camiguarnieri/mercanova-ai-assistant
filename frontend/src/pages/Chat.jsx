/** Vista de chat: la conversación con el asistente de compras. */

import { useCallback, useEffect, useRef, useState } from 'react'

import { sendChatMessage } from '../api/client.js'
import { useCart } from '../CartContext.jsx'
import CartPanel from '../components/CartPanel.jsx'
import ChatMessage, { ASSISTANT, ERROR, USER } from '../components/ChatMessage.jsx'
import { Empty } from '../components/Notice.jsx'
import VoiceInput from '../components/VoiceInput.jsx'

/** Las herramientas con las que el asistente escribe el carrito. */
const CART_TOOLS = ['add_to_cart', 'remove_from_cart']

export default function Chat({ onGoToCart }) {
  // La sesión es la del carrito: la misma que usa el chat para su historial.
  const { sessionId, refresh } = useCart()
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  // Para numerar los mensajes: el texto se puede repetir, la clave no.
  const lastId = useRef(0)
  const endRef = useRef(null)
  const inputRef = useRef(null)

  // Deja a la vista lo último que se dijo, como cualquier chat.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [messages, sending])

  // Agrega un mensaje al final de la conversación.
  function append(message) {
    lastId.current += 1
    const id = lastId.current
    setMessages((previous) => [...previous, { id, ...message }])
  }

  // Escribe en el campo lo que se dictó, sin mandarlo: lo revisa el usuario.
  // Si ya había texto, lo que se dictó se agrega al final.
  const handleTranscript = useCallback((text) => {
    setDraft((previous) => (previous.trim() === '' ? text : `${previous.trim()} ${text}`))
    inputRef.current?.focus()
  }, [])

  // Manda el mensaje y agrega la respuesta, o el error, a la conversación.
  async function handleSubmit(event) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || sending) {
      return
    }

    setDraft('')
    append({ role: USER, text })
    setSending(true)
    try {
      const answer = await sendChatMessage(sessionId, text)
      append({
        role: ASSISTANT,
        text: answer.reply,
        products: answer.products,
        comparisons: answer.comparisons,
        toolsUsed: answer.tools_used,
      })
      // El carrito no viaja en la respuesta del chat: lo arma un solo
      // endpoint. Si el asistente lo tocó, se lo vuelve a pedir, así el panel
      // muestra lo que quedó guardado y no lo que dijo el modelo.
      if ((answer.tools_used || []).some((tool) => CART_TOOLS.includes(tool.name))) {
        refresh()
      }
    } catch (cause) {
      // El mensaje de la API ya explica qué hacer: se muestra tal cual.
      append({ role: ERROR, text: cause.message })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="chat-layout">
      <section className="chat">
        <div className="chat-messages">
          {messages.length === 0 ? (
            <Empty title="Contale qué estás buscando">
              Por ejemplo: "necesito auriculares para viajar, hasta 200 dólares". Debajo de
              cada respuesta vas a ver qué consultó en el catálogo.
            </Empty>
          ) : (
            messages.map((message) => <ChatMessage key={message.id} message={message} />)
          )}

          {sending ? (
            <p className="chat-pending" role="status">
              <span className="spinner" aria-hidden="true" />
              Consultando el catálogo...
            </p>
          ) : null}

          <div ref={endRef} />
        </div>

        <form className="chat-form" onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Escribí o dictá lo que necesitás y apretá Enter"
            aria-label="Mensaje para el asistente"
            autoComplete="off"
          />
          <VoiceInput onTranscript={handleTranscript} disabled={sending} />
          <button type="submit" disabled={sending || draft.trim() === ''}>
            {sending ? 'Enviando...' : 'Enviar'}
          </button>
        </form>
      </section>

      {/* El carrito queda a la vista mientras se conversa: el asistente lo
          puede tocar, y lo que agrega se ve acá sin recargar. */}
      <aside className="chat-cart">
        <CartPanel
          title="Carrito"
          action={
            <div className="checkout-actions">
              <button type="button" className="button-secondary" onClick={onGoToCart}>
                Ir al carrito y comprar
              </button>
            </div>
          }
        />
      </aside>
    </div>
  )
}
