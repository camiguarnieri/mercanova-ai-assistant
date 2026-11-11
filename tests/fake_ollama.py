"""Dobles del cliente de Ollama, compartidos por los tests.

Ningún test prende Ollama ni sale a la red: se reemplaza el cliente por uno de
estos, que devuelve respuestas preparadas y guarda lo que se le mandó.
"""

from __future__ import annotations

from typing import Any


class FakeFunction:
    """La función que el modelo dice querer invocar."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.name = name
        self.arguments = arguments


class FakeCall:
    """Una invocación de herramienta pedida por el modelo."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    """El mensaje que devuelve el modelo."""

    def __init__(self, content: str = "", tool_calls: list[FakeCall] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class FakeResponse:
    """La respuesta de `chat()`."""

    def __init__(self, message: FakeMessage | None) -> None:
        self.message = message


class FakeClient:
    """Cliente que devuelve respuestas preparadas y guarda lo que recibió."""

    def __init__(self, *, responses: list[FakeResponse] | None = None, **kwargs: Any) -> None:
        self.host = kwargs.get("host")
        # Se guarda para poder verificar que `create_client()` lo manda: sin un
        # timeout, httpx espera para siempre.
        self.timeout = kwargs.get("timeout")
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> FakeResponse:
        # Se guarda una copia de los mensajes: la lista que recibe se sigue
        # llenando entre vueltas, y si no se copia todas apuntan a lo mismo.
        self.calls.append({**kwargs, "messages": list(kwargs.get("messages") or [])})
        if not self.responses:
            return FakeResponse(FakeMessage(content="Listo."))
        return self.responses.pop(0)


# Devuelve un cliente que pide una herramienta y después responde.
def client_with_one_tool_call(
    name: str, arguments: dict[str, Any], reply: str = "Te recomiendo ese producto."
) -> FakeClient:
    """Arma el doble para una conversación de una vuelta de herramientas.

    Args:
        name: Herramienta que el modelo va a pedir.
        arguments: Argumentos con los que la va a pedir.
        reply: Lo que contesta después de ver el resultado.

    Returns:
        El cliente falso, con las dos respuestas ya cargadas.
    """
    return FakeClient(
        responses=[
            FakeResponse(FakeMessage(tool_calls=[FakeCall(name, arguments)])),
            FakeResponse(FakeMessage(content=reply)),
        ]
    )


# Devuelve un cliente que busca primero y después usa un product_id.
def client_after_searching(
    name: str, arguments: dict[str, Any], *, reply: str = "Listo.", category: str = "Monitors"
) -> FakeClient:
    """Arma el doble para una conversación que busca antes de usar un id.

    Una herramienta solo acepta un product_id que haya salido de un resultado
    anterior, así que para probar las que reciben uno hay que buscar primero.

    Args:
        name: La herramienta que se invoca después de buscar.
        arguments: Los argumentos con los que se la invoca.
        reply: Lo que contesta el modelo al final.
        category: La categoría con la que busca en el primer paso.

    Returns:
        El cliente falso, con las tres respuestas ya cargadas.
    """
    return FakeClient(
        responses=[
            FakeResponse(
                FakeMessage(tool_calls=[FakeCall("search_products", {"category": category})])
            ),
            FakeResponse(FakeMessage(tool_calls=[FakeCall(name, arguments)])),
            FakeResponse(FakeMessage(content=reply)),
        ]
    )


# Devuelve un cliente que busca, pide relacionados y después compara.
def client_that_compares(reply: str = "El primero cancela ruido y el segundo no.") -> FakeClient:
    """Arma el doble de una conversación que termina en una comparación.

    Son tres pasos porque los dos product_id tienen que tener procedencia: uno
    sale de la búsqueda y el otro de los productos relacionados.

    Args:
        reply: Lo que contesta el modelo al final.

    Returns:
        El cliente falso, con las cuatro respuestas ya cargadas.
    """
    return FakeClient(
        responses=[
            FakeResponse(
                FakeMessage(tool_calls=[FakeCall("search_products", {"category": "Monitors"})])
            ),
            FakeResponse(
                FakeMessage(
                    tool_calls=[FakeCall("get_related_products", {"product_id": "MN-MON-0001"})]
                )
            ),
            FakeResponse(
                FakeMessage(
                    tool_calls=[
                        FakeCall(
                            "compare_products",
                            {"product_ids": ["MN-HDP-0001", "MN-HDP-0002"]},
                        )
                    ]
                )
            ),
            FakeResponse(FakeMessage(content=reply)),
        ]
    )


# Devuelve un cliente que contesta sin pedir ninguna herramienta.
def client_that_answers(reply: str) -> FakeClient:
    """Arma el doble para una respuesta directa, sin herramientas.

    Args:
        reply: Lo que contesta el modelo.

    Returns:
        El cliente falso, con esa única respuesta cargada.
    """
    return FakeClient(responses=[FakeResponse(FakeMessage(content=reply))])
