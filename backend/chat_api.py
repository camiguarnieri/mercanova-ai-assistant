"""Endpoint del asistente conversacional.

Solo traduce el pedido HTTP y los errores: el turno lo corre `assistant.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend import assistant, carts, llm, sessions, vocabulary
from backend.chat_models import ChatRequest, ChatResponse
from backend.dependencies import (
    ConnectionScope,
    get_cart_store,
    get_connection_scope,
    get_session_store,
    get_vocabulary,
)

router = APIRouter()

# Ollama apagado o modelo sin instalar: el servicio no está listo, no es un bug.
LLM_UNAVAILABLE_STATUS = 503


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Conversa con el asistente de compras",
    responses={
        LLM_UNAVAILABLE_STATUS: {
            "description": "Ollama no está disponible o el modelo no llegó a responder."
        }
    },
)
def post_chat(
    request: ChatRequest,
    connection_scope: ConnectionScope = Depends(get_connection_scope),
    store: sessions.SessionStore = Depends(get_session_store),
    cart_store: carts.CartStore = Depends(get_cart_store),
    terms: vocabulary.Vocabulary = Depends(get_vocabulary),
) -> ChatResponse:
    """Contesta un mensaje y devuelve las herramientas que usó para contestarlo.

    La conversación se guarda en el servidor, en memoria, indexada por
    `session_id`: **se pierde cuando se reinicia la API**. El cliente solo
    manda el mensaje nuevo, no el historial.

    El asistente puede agregar y quitar productos del carrito de esa misma
    sesión. El carrito no viaja en esta respuesta: lo devuelve `GET /cart`, que
    es el único lugar donde se arma, así la pantalla y el asistente no pueden
    mostrar dos carritos distintos. El frontend lo vuelve a pedir cuando
    `tools_used` trae una herramienta del carrito.

    Los errores de la capa del modelo se devuelven como 503 con el mensaje
    accionable que trae la excepción, para que el frontend lo muestre tal cual
    en vez de recibir un 500 sin explicación.
    """
    with connection_scope() as connection:
        try:
            turn = assistant.respond(
                connection,
                store,
                request.session_id,
                request.message,
                vocabulary=terms,
                carts=cart_store,
            )
        except llm.LLMError as error:
            raise HTTPException(
                status_code=LLM_UNAVAILABLE_STATUS, detail=str(error)
            ) from error

    return ChatResponse(
        session_id=request.session_id,
        reply=turn.reply,
        products=turn.products,
        comparisons=turn.comparisons,
        tools_used=turn.tools_used,
    )
