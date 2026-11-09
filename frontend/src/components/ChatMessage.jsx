/** Un mensaje de la conversación: del usuario, del asistente o un error. */

import ComparisonTable from './ComparisonTable.jsx'
import ProductCards from './ProductCards.jsx'
import ToolTrace from './ToolTrace.jsx'

/** Quién escribió cada mensaje. */
export const USER = 'user'
export const ASSISTANT = 'assistant'
export const ERROR = 'error'

/** Cómo se presenta cada autor en la burbuja. */
const AUTHORS = {
  [USER]: 'Vos',
  [ASSISTANT]: 'Asistente',
  [ERROR]: 'No se pudo responder',
}

export default function ChatMessage({ message }) {
  const isAssistant = message.role === ASSISTANT

  return (
    <article
      className={`message message-${message.role}`}
      role={message.role === ERROR ? 'alert' : undefined}
    >
      <p className="message-author">{AUTHORS[message.role]}</p>
      <p className="message-text">{message.text}</p>
      {/* Las tarjetas y la tabla van antes de la traza y después del texto:
          son el dato que respalda lo que acaba de decir el asistente. */}
      {isAssistant ? <ProductCards products={message.products} /> : null}
      {isAssistant
        ? (message.comparisons || []).map((comparison, index) => (
            <ComparisonTable key={index} comparison={comparison} />
          ))
        : null}
      {isAssistant ? <ToolTrace tools={message.toolsUsed} /> : null}
    </article>
  )
}
