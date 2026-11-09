"""Acceso a Ollama, encapsulado.

Es el único módulo que habla con el modelo. No sabe nada del catálogo: quien lo
usa le pasa las definiciones de las herramientas y una función que las ejecuta,
así que se puede probar sin Ollama prendido y sin base de datos.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from typing import Any

from ollama import Client, RequestError, ResponseError

from backend.prompts import SYSTEM_PROMPT

# qwen2.5:3b es el que mejor elige las herramientas de los que probamos, y entra
# en CPU sin que una consulta se vaya de tiempo. llama3.1 respeta más el esquema
# pero son 8B: pide bastante más memoria y en CPU tarda varias veces más.
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_HOST = "http://localhost:11434"

# Ventana de contexto con la que se carga el modelo. El prompt del sistema más
# los esquemas de las herramientas ocupan unos 2800 tokens, así que con los
# 4096 de la mayoría de los defaults queda muy poco lugar para la conversación
# y los resultados de las herramientas, y Ollama empieza a truncar.
DEFAULT_NUM_CTX = 8192

# Cuántas veces se le permite al modelo pedir herramientas antes de responder.
MAX_TOOL_STEPS = 5

# Tiempo que Ollama mantiene el modelo en memoria después de usarlo. Cargarlo
# cuesta unos segundos y se paga en el primer mensaje: con 10m una conversación
# que se retoma más tarde lo vuelve a pagar.
DEFAULT_KEEP_ALIVE = "30m"



class LLMError(RuntimeError):
    """Error de la capa que habla con el modelo."""


class LLMConfigurationError(LLMError):
    """Ollama no está disponible o el modelo no está instalado."""


class LLMResponseError(LLMError):
    """El modelo contestó algo que no se puede usar."""


# Devuelve el modelo configurado, con default seguro.
def model_name() -> str:
    """Resuelve el nombre del modelo.

    Returns:
        El valor de `OLLAMA_MODEL`, o `DEFAULT_MODEL` si no está definido.
    """
    return (os.getenv("OLLAMA_MODEL") or "").strip() or DEFAULT_MODEL


# Devuelve el host de Ollama, con default seguro.
def host() -> str:
    """Resuelve el host de Ollama.

    Returns:
        El valor de `OLLAMA_HOST`, o `DEFAULT_HOST` si no está definido.
    """
    return (os.getenv("OLLAMA_HOST") or "").strip() or DEFAULT_HOST


# Lee una variable de entorno con un número de tokens, o avisa qué está mal.
def token_count(name: str, default: int | None) -> int | None:
    """Resuelve una variable de entorno que lleva una cantidad de tokens.

    Args:
        name: Nombre de la variable de entorno.
        default: Valor a usar si no está definida, o `None` si en ese caso la
            opción no se manda y la decide Ollama.

    Returns:
        El valor configurado, o `default` si la variable está vacía.

    Raises:
        LLMConfigurationError: Si la variable está definida y no es un entero
            positivo. No se cae al default a propósito: si alguien la bajó para
            que el modelo entre en memoria, usar el default por su cuenta es
            peor que avisar que el valor está mal escrito.
    """
    configured = (os.getenv(name) or "").strip()
    if not configured:
        return default
    fallback = (
        f"Dejala vacía para usar {default}."
        if default is not None
        else "Dejala vacía para que lo decida Ollama."
    )
    try:
        value = int(configured)
    except ValueError as error:
        raise LLMConfigurationError(
            f"{name} tiene que ser un número entero de tokens, y llegó "
            f"'{configured}'. {fallback}"
        ) from error
    if value <= 0:
        raise LLMConfigurationError(
            f"{name} tiene que ser mayor que cero, y llegó {value}. {fallback}"
        )
    return value


# Devuelve el tamaño de la ventana de contexto, con default seguro.
def num_ctx() -> int:
    """Resuelve la ventana de contexto con la que se carga el modelo.

    Returns:
        El valor de `OLLAMA_NUM_CTX`, o `DEFAULT_NUM_CTX` si no está definido.

    Raises:
        LLMConfigurationError: Si la variable no es un entero positivo.
    """
    configured = token_count("OLLAMA_NUM_CTX", DEFAULT_NUM_CTX)
    return DEFAULT_NUM_CTX if configured is None else configured


# Devuelve el tope de tokens de la respuesta, si alguien lo configuró.
def num_predict() -> int | None:
    """Resuelve cuántos tokens como máximo escribe el modelo.

    No tiene valor por defecto a propósito. Probamos con 300 y cortó una
    respuesta a mitad de palabra: en CPU cada token generado se paga en tiempo,
    pero una respuesta truncada es peor que una lenta. Sin la variable no se
    manda la opción y el tope lo decide Ollama.

    Returns:
        El valor de `OLLAMA_NUM_PREDICT`, o `None` si no está definido.

    Raises:
        LLMConfigurationError: Si la variable no es un entero positivo.
    """
    return token_count("OLLAMA_NUM_PREDICT", None)


# Devuelve cuánto tiempo Ollama deja el modelo cargado, con default seguro.
def keep_alive() -> str:
    """Resuelve cuánto tiempo el modelo queda en memoria después de usarlo.

    No se valida el formato: lo interpreta Ollama, que acepta una duración
    ("30m", "1h"), un número de segundos o "-1" para que no lo descargue nunca.
    Validarlo acá sería adivinar su gramática.

    Returns:
        El valor de `OLLAMA_KEEP_ALIVE`, o `DEFAULT_KEEP_ALIVE` si no está
        definido.
    """
    return (os.getenv("OLLAMA_KEEP_ALIVE") or "").strip() or DEFAULT_KEEP_ALIVE


# Arma las opciones de generación que viajan en cada llamada al modelo.
def options() -> dict[str, Any]:
    """Devuelve las opciones con las que se le pide al modelo que responda.

    Returns:
        Temperatura 0, para que las respuestas se basen en los datos de las
        herramientas y no en la creatividad del modelo, y la ventana de
        contexto configurada. `num_predict` se agrega solo si alguien lo
        configuró: sin la variable el tope lo decide Ollama.

    Raises:
        LLMConfigurationError: Si `OLLAMA_NUM_CTX` o `OLLAMA_NUM_PREDICT` no
            sirven.
    """
    chosen = {"temperature": 0, "num_ctx": num_ctx()}
    limit = num_predict()
    if limit is not None:
        chosen["num_predict"] = limit
    return chosen


# Crea el cliente apuntado al host configurado.
def create_client() -> Client:
    """Crea el cliente de Ollama.

    Returns:
        El cliente, apuntado al host de `host()`.
    """
    return Client(host=host())


# Traduce los errores de Ollama a mensajes que digan qué hacer.
def translate_error(error: Exception) -> LLMConfigurationError:
    """Convierte un error de la librería en uno de este proyecto.

    Args:
        error: La excepción que levantó la librería `ollama`.

    Returns:
        El error con el mensaje accionable, listo para levantar.
    """
    model = model_name()
    detail = str(error)
    if isinstance(error, ResponseError) and (
        error.status_code == 404 or "not found" in detail.lower()
    ):
        return LLMConfigurationError(
            f"No se encontró el modelo '{model}' en Ollama. Instalalo con: ollama pull {model}"
        )
    return LLMConfigurationError(
        f"No se pudo hablar con Ollama en {host()}. Verificá que esté corriendo "
        f"(ollama serve) y que OLLAMA_HOST apunte ahí. Detalle: {detail}"
    )


# Carga el modelo en memoria para que la primera consulta no pague la espera.
def preload_model(client: Client | None = None) -> None:
    """Deja el modelo cargado en memoria.

    Ollama carga el modelo recién en el primer pedido, y eso tarda unos
    segundos. Con una llamada sin mensajes queda cargado antes de que el
    usuario pregunte.

    Se mandan las mismas opciones que en una conversación: Ollama carga el
    modelo con la ventana de contexto del pedido, así que precargarlo con otra
    lo obligaría a recargarse en el primer mensaje y la precarga no serviría de
    nada.

    Args:
        client: Cliente a usar. Si es `None` se crea uno con `create_client()`.

    Raises:
        LLMConfigurationError: Si Ollama no responde, el modelo no está o
            `OLLAMA_NUM_CTX` no sirve.
    """
    target = client or create_client()
    try:
        target.chat(
            model=model_name(), messages=[], options=options(), keep_alive=keep_alive()
        )
    except (ResponseError, RequestError, ConnectionError, OSError) as error:
        raise translate_error(error) from error


# Lee las herramientas que pidió el modelo en su respuesta.
def tool_calls_of(message: Any) -> list[Any]:
    """Saca las invocaciones de herramientas de un mensaje del modelo.

    Args:
        message: El mensaje que devolvió `chat()`.

    Returns:
        Las invocaciones pedidas, o una lista vacía si no pidió ninguna.
    """
    return list(getattr(message, "tool_calls", None) or [])


# Corre el ciclo de tool calling hasta que el modelo responda o se corte.
def run_conversation(
    messages: list[dict[str, Any]],
    *,
    tools: Sequence[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], Any],
    client: Client | None = None,
    max_steps: int = MAX_TOOL_STEPS,
) -> list[dict[str, Any]]:
    """Conversa con el modelo, ejecutando las herramientas que pida.

    El modelo puede pedir varias herramientas antes de contestar. Cada vuelta
    se le devuelven los resultados y se le vuelve a preguntar, hasta que
    responda en texto o se agoten los pasos.

    Args:
        messages: La conversación hasta ahora, en el formato de Ollama. Se
            copia: no se modifica la lista que recibe.
        tools: Las definiciones de las herramientas disponibles.
        execute_tool: Función que recibe nombre y argumentos y devuelve el
            resultado, que se serializa a JSON para el modelo.
        client: Cliente a usar. Si es `None` se crea uno con `create_client()`.
        max_steps: Cuántas vueltas de herramientas se permiten.

    Returns:
        La conversación completa, con los mensajes del modelo, los resultados
        de las herramientas y la respuesta final al final de la lista.

    Raises:
        LLMConfigurationError: Si Ollama no responde o el modelo no está.
        LLMResponseError: Si el modelo sigue pidiendo herramientas después de
            `max_steps` vueltas, o si contesta sin contenido.
    """
    target = client or create_client()
    history = list(messages)

    for _ in range(max_steps + 1):
        try:
            response = target.chat(
                model=model_name(),
                messages=history,
                tools=tools,
                options=options(),
                keep_alive=keep_alive(),
            )
        except (ResponseError, RequestError, ConnectionError, OSError) as error:
            raise translate_error(error) from error

        message = getattr(response, "message", None)
        if message is None:
            raise LLMResponseError(
                "Ollama devolvió una respuesta sin mensaje. Probá de nuevo; si sigue, "
                "revisá la versión de Ollama y del modelo."
            )

        calls = tool_calls_of(message)
        history.append(
            {
                "role": "assistant",
                "content": message.content or "",
                **({"tool_calls": calls} if calls else {}),
            }
        )
        if not calls:
            if not (message.content or "").strip():
                raise LLMResponseError(
                    "El modelo respondió vacío y sin pedir herramientas. Probá reformular "
                    "la consulta."
                )
            return history

        for call in calls:
            history.append(run_tool_call(call, execute_tool))

    raise LLMResponseError(
        f"El modelo siguió pidiendo herramientas después de {max_steps} vueltas y no "
        f"llegó a una respuesta. Reformulá la consulta o subí max_steps."
    )


# Ejecuta una invocación y la convierte en el mensaje que espera el modelo.
def run_tool_call(
    call: Any, execute_tool: Callable[[str, dict[str, Any]], Any]
) -> dict[str, Any]:
    """Corre una herramienta pedida por el modelo.

    Args:
        call: La invocación que vino en el mensaje del modelo.
        execute_tool: Función que ejecuta la herramienta.

    Returns:
        El mensaje con rol `tool` y el resultado serializado en JSON.
    """
    # El modelo puede pedir una herramienta sin nombre. No se completa con nada:
    # queda en vacío, el router devuelve que no existe y la interfaz no la
    # muestra, porque no hubo ninguna consulta al catálogo que mostrar.
    name = str(getattr(call.function, "name", None) or "")
    arguments = dict(call.function.arguments or {})
    result = execute_tool(name, arguments)
    return {
        "role": "tool",
        "tool_name": name,
        "content": json.dumps(result, ensure_ascii=False, default=str),
    }


# Arma la conversación inicial con el prompt del sistema.
def start_conversation(user_message: str, system_prompt: str = SYSTEM_PROMPT) -> list[dict]:
    """Crea la conversación con el prompt del sistema y el primer mensaje.

    Args:
        user_message: Lo que escribió el usuario.
        system_prompt: Instrucciones del sistema. Por defecto `SYSTEM_PROMPT`.

    Returns:
        Los dos mensajes iniciales, en el formato de Ollama.
    """
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
