/** Vista de chat: la conversación con el asistente de compras. */

import { useEffect, useRef, useState } from 'react'

import { sendChatMessage } from '../api/client.js'
import ChatMessage, { ASSISTANT, ERROR, USER } from '../components/ChatMessage.jsx'
import { Empty } from '../components/Notice.jsx'
import { getSessionId } from '../session.js'

export default function Chat() {
  // El identificador se crea una sola vez y queda guardado en el navegador.
  const [sessionId] = useState(getSessionId)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  // Para numerar los mensajes: el texto se puede repetir, la clave no.
  const lastId = useRef(0)
  const endRef = useRef(null)

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
    } catch (cause) {
      // El mensaje de la API ya explica qué hacer: se muestra tal cual.
      append({ role: ERROR, text: cause.message })
    } finally {
      setSending(false)
    }
  }

  return (
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
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Escribí lo que necesitás y apretá Enter"
          aria-label="Mensaje para el asistente"
          autoComplete="off"
        />
        <button type="submit" disabled={sending || draft.trim() === ''}>
          {sending ? 'Enviando...' : 'Enviar'}
        </button>
      </form>
    </section>
  )
}
