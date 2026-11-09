"""Un turno de conversación: historial, ciclo de herramientas y respuesta.

Junta las piezas que ya existen —`sessions`, `llm`, `tool_router`— y no agrega
reglas propias. Es lo único que sabe que una conversación tiene continuidad.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ollama import Client

from backend import llm, model_view, product_lookup, provenance, tool_router, tool_schemas
from backend.carts import CartSession, CartStore
from backend.chat_models import AssistantTurn, Comparison, ShownProduct, ToolInvocation
from backend.sessions import Message, SessionStore
from backend.vocabulary import Vocabulary


# Arma los mensajes a mandar: la conversación guardada más lo nuevo que escribió.
def build_messages(history: list[Message] | None, message: str) -> list[Message]:
    """Agrega el mensaje del usuario a la conversación de la sesión.

    La conversación viaja entera. Probamos recortarla —el prompt del sistema más
    los últimos turnos, descartando los resultados de herramientas viejos— y la
    medición no lo respaldó: no mejoró el tiempo y el modelo dejó de llamar
    herramientas. Está escrito en `docs/decision-recorte-historial.md`, con los
    números, para no volver a intentarlo sin leerlo.

    Args:
        history: La conversación guardada, o `None` si es la primera vuelta.
        message: Lo que escribió el usuario.

    Returns:
        Los mensajes para `llm.run_conversation()`. Si la sesión es nueva
        empiezan con el prompt del sistema.
    """
    if history is None:
        return llm.start_conversation(message)
    return [*history, {"role": "user", "content": message}]


# Convierte un resultado en el mensaje de herramienta que lee el modelo.
def tool_message(name: str, result: Any) -> Message:
    """Arma el mensaje con rol `tool` que ve el modelo.

    El resultado pasa por `model_view.for_the_model()`: la interfaz lo usa
    entero y al modelo le llega sin los campos que se le cruzaban de un
    producto a otro.

    Args:
        name: Nombre con el que se identifica la consulta.
        result: Lo que devolvió, completo.

    Returns:
        El mensaje en el formato de Ollama, con el resultado en JSON.
    """
    return {
        "role": "tool",
        "tool_name": name,
        "content": json.dumps(
            model_view.for_the_model(result), ensure_ascii=False, default=str
        ),
    }


# Saca de un resultado los productos que la interfaz muestra como tarjetas.
def shown_products(result: Any) -> list[ShownProduct]:
    """Lista los productos de un resultado de búsqueda.

    La tarjeta la imprime el sistema con estos datos, así que deja de importar
    lo que escriba el modelo sobre el precio, el stock o para qué sirve cada
    producto: el dato que ve el usuario sale del catálogo.

    Args:
        result: Lo que devolvió la herramienta.

    Returns:
        Los productos del resultado, o una lista vacía si no trae ninguno.
    """
    if not isinstance(result, dict) or not result.get("found"):
        return []
    products = result.get("products")
    if not isinstance(products, list):
        return []
    return [
        ShownProduct.model_validate(product)
        for product in products
        if isinstance(product, dict)
    ]


# Deja un producto por identificador, en el orden en que aparecieron.
def unique_products(products: list[ShownProduct]) -> list[ShownProduct]:
    """Saca los repetidos de las búsquedas de un mismo turno.

    Args:
        products: Los productos que aparecieron, con repetidos.

    Returns:
        Uno por `product_id`, en el orden en que el modelo los vio.
    """
    seen: dict[str, ShownProduct] = {}
    for product in products:
        seen.setdefault(product.product_id, product)
    return list(seen.values())


# Convierte el resultado de compare_products en lo que muestra la tabla.
def comparison_of(name: str, result: Any) -> Comparison | None:
    """Saca la comparación de un resultado de herramienta, si la hay.

    La tabla de la interfaz se arma con esto y no con la respuesta del modelo,
    que al escribirla en prosa dio vuelta un valor.

    Args:
        name: Nombre de la herramienta que se ejecutó.
        result: Lo que devolvió.

    Returns:
        La comparación lista para mandar al frontend, o `None` si la
        herramienta no era `compare_products` o si falló.
    """
    if name != tool_schemas.COMPARE_PRODUCTS or not isinstance(result, dict):
        return None
    if not result.get("found") or not result.get("products"):
        return None
    return Comparison.model_validate(
        {
            "products": result["products"],
            "specifications": result.get("shared_specifications", []),
        }
    )


# Contesta un mensaje del usuario y deja la conversación guardada.
def respond(
    connection: sqlite3.Connection,
    store: SessionStore,
    session_id: str,
    message: str,
    *,
    vocabulary: Vocabulary,
    carts: CartStore | None = None,
    client: Client | None = None,
) -> AssistantTurn:
    """Corre un turno de la conversación de una sesión.

    Las herramientas se ejecutan contra la conexión que se recibe, y cada
    invocación se registra para devolverla junto con la respuesta: es la
    evidencia de que los datos salieron del catálogo.

    Un product_id solo se acepta si apareció en un resultado anterior de esta
    conversación, así que el modelo no puede inventar uno ni acertarlo de
    casualidad.

    Lo que devuelve cada herramienta se usa entero para armar las tarjetas y la
    tabla, y al modelo le llega filtrado por `model_view.for_the_model()`.

    Si el turno falla, la sesión queda como estaba: no se guarda una
    conversación a medias ni los identificadores que aparecieron en ella.

    Args:
        connection: Conexión abierta con `db.connect()`, válida en este hilo.
        store: Dónde está guardada la conversación de la sesión.
        session_id: Identificador de la conversación.
        message: Lo que escribió el usuario.
        vocabulary: De dónde salen las definiciones de las herramientas, con
            los valores válidos del catálogo adentro.
        carts: Dónde están guardados los carritos. El de esta sesión es el
            único que el modelo puede tocar, y lo ata el servidor: el
            `session_id` no es un argumento de la herramienta. Si es `None`,
            las herramientas del carrito devuelven un error y la conversación
            sigue con las que leen el catálogo.
        client: Cliente de Ollama. Si es `None`, `llm` crea uno.

    Returns:
        La respuesta del asistente y las herramientas que ejecutó, en orden.

    Raises:
        llm.LLMConfigurationError: Si Ollama no responde o falta el modelo.
        llm.LLMResponseError: Si el modelo no llega a una respuesta usable.
    """
    used: list[ToolInvocation] = []
    comparisons: list[Comparison] = []
    found_products: list[ShownProduct] = []
    # Los product_id que el modelo ya vio. Arranca con los de los turnos
    # anteriores y crece con cada resultado: una herramienta no acepta un
    # identificador que no esté acá.
    known_products = store.known_products(session_id)
    # El carrito que pueden escribir las herramientas es el de esta sesión y
    # ninguno más: el modelo no elige de cuál se trata.
    cart_session = None if carts is None else CartSession(carts, session_id)

    # Se envuelve el router para anotar qué se ejecutó, sin que `llm` tenga que
    # saber nada de esto. Se anotan los argumentos ya normalizados: son los que
    # usó la herramienta.
    def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
        result = tool_router.run_tool(
            connection, name, arguments, known_products, cart_session
        )
        known_products.update(provenance.collect_ids(result))
        comparison = comparison_of(name, result)
        if comparison is not None:
            comparisons.append(comparison)
        if name == tool_schemas.SEARCH_PRODUCTS:
            found_products.extend(shown_products(result))
        used.append(
            ToolInvocation(name=name, arguments=tool_router.arguments_for_trace(name, arguments))
        )
        # La tarjeta y la tabla se arman con el resultado entero, de arriba; al
        # modelo le vuelve sin los campos que se le cruzaban entre productos.
        return model_view.for_the_model(result)

    messages = build_messages(store.history(session_id), message)

    # Si el usuario nombró un producto, el catálogo se consulta antes de que el
    # modelo decida: con dos modelos distintos no lo buscaba y contestaba que
    # no tenía información. El resultado entra como un mensaje de herramienta,
    # así el modelo arranca el turno con el dato en la mano.
    lookup = product_lookup.lookup_message(connection, message)
    if lookup is not None:
        messages.append(tool_message(product_lookup.TOOL_NAME, lookup))
        known_products.update(provenance.collect_ids(lookup))
        found_products.extend(shown_products(lookup))
        used.append(
            ToolInvocation(name=product_lookup.TOOL_NAME, arguments={"message": message})
        )

    history = llm.run_conversation(
        messages,
        tools=vocabulary.schemas(connection),
        execute_tool=execute_tool,
        client=client,
    )
    store.save(session_id, history)
    store.remember_products(session_id, known_products)
    return AssistantTurn(
        reply=history[-1]["content"],
        products=unique_products(found_products),
        comparisons=comparisons,
        tools_used=used,
    )
