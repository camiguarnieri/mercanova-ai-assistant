"""Normalización de los argumentos que manda el modelo.

Un modelo chico corriendo en local no siempre respeta el esquema: manda la
palabra "null" en vez de omitir un parámetro opcional, y los números como
texto. Esto lo arregla antes de validar, así una herramienta no falla por la
forma en que vino el argumento y no por lo que pidió el usuario.

Acá no se consulta nada ni se decide qué herramienta correr: eso es de
`tool_router.py`.
"""

from __future__ import annotations

from typing import Any

from backend.tools import ToolArgumentError

__all__ = ["ABSENT_TEXTS", "is_absent", "coerce", "normalize_arguments"]

# Textos con los que el modelo dice "este parámetro no va". No distingue
# mayúsculas. Ojo: esto vale para los argumentos de las herramientas, no para
# los valores del catálogo, donde el texto "None" sí significa algo.
ABSENT_TEXTS = frozenset({"", "null", "none", "undefined", "nil"})


# Dice si un valor hay que tratarlo como si no hubiera llegado.
def is_absent(value: Any) -> bool:
    """Decide si un argumento está ausente en la práctica.

    Args:
        value: El valor tal como lo mandó el modelo.

    Returns:
        `True` si es `None`, un texto vacío o uno de los textos con los que el
        modelo escribe "nada", como 'null' o 'undefined'.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ABSENT_TEXTS
    return False


# Convierte un texto numérico al entero que declara el esquema.
def to_integer(tool: str, parameter: str, value: Any) -> int:
    """Convierte un valor al entero que espera el esquema.

    Args:
        tool: Nombre de la herramienta, para el mensaje de error.
        parameter: Nombre del parámetro.
        value: El valor que mandó el modelo, por ejemplo `'5'`.

    Returns:
        El valor como entero.

    Raises:
        ToolArgumentError: Si el valor no representa un número.
    """
    if isinstance(value, bool):
        raise ToolArgumentError(
            f"Volvé a invocar '{tool}' con un número entero en '{parameter}', sin "
            f"comillas; esta vez llegó {value!r}. Si no sabés qué número va, no mandes "
            f"el parámetro."
        )
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError) as error:
        raise ToolArgumentError(
            f"Volvé a invocar '{tool}' con un número entero en '{parameter}', sin "
            f"comillas; esta vez llegó {value!r}. Si no sabés qué número va, no mandes "
            f"el parámetro."
        ) from error


# Convierte un texto numérico al número decimal que declara el esquema.
def to_number(tool: str, parameter: str, value: Any) -> float:
    """Convierte un valor al número que espera el esquema.

    Args:
        tool: Nombre de la herramienta, para el mensaje de error.
        parameter: Nombre del parámetro.
        value: El valor que mandó el modelo, por ejemplo `'200'`.

    Returns:
        El valor como número decimal.

    Raises:
        ToolArgumentError: Si el valor no representa un número.
    """
    if isinstance(value, bool):
        raise ToolArgumentError(
            f"Volvé a invocar '{tool}' con un número en '{parameter}', sin comillas y "
            f"sin la moneda; esta vez llegó {value!r}. Si el usuario no dio un número, "
            f"no mandes el parámetro."
        )
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ToolArgumentError(
            f"Volvé a invocar '{tool}' con un número en '{parameter}', sin comillas y "
            f"sin la moneda; esta vez llegó {value!r}. Si el usuario no dio un número, "
            f"no mandes el parámetro."
        ) from error


# Convierte a lista lo que el modelo escribió como texto.
def to_array(value: Any) -> list[Any]:
    """Convierte al arreglo que espera el esquema.

    El modelo manda la lista escrita, como `"['MN-HDP-0001', 'MN-HDP-0009']"`,
    que no es JSON válido por las comillas simples. Se separa por comas y se
    limpian los corchetes y las comillas, que es lo que hace falta para una
    lista de identificadores.

    Args:
        value: El valor que mandó el modelo.

    Returns:
        El valor como lista. Un identificador suelto queda en una lista de uno,
        así la herramienta puede decir cuántos esperaba en vez de fallar por el
        tipo.
    """
    if isinstance(value, (list, tuple)):
        return list(value)

    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    pieces = (piece.strip().strip("'\"").strip() for piece in text.split(","))
    return [piece for piece in pieces if piece]


# Lleva el valor al tipo que declara el esquema de la herramienta.
def coerce(tool: str, parameter: str, declared_type: str | None, value: Any) -> Any:
    """Convierte un argumento al tipo declarado, si hace falta.

    Se convierten los numéricos y los arreglos: son los que el modelo manda
    como texto. Los demás pasan tal cual, y si el tipo no sirve lo rechaza la
    herramienta, que es la que sabe qué hacer con cada uno.

    Args:
        tool: Nombre de la herramienta.
        parameter: Nombre del parámetro.
        declared_type: El `type` del esquema JSON, o `None` si no lo declara.
        value: El valor que mandó el modelo.

    Returns:
        El valor convertido al tipo declarado.

    Raises:
        ToolArgumentError: Si se declara numérico y el valor no lo es.
    """
    if declared_type == "integer":
        return to_integer(tool, parameter, value)
    if declared_type == "number":
        return to_number(tool, parameter, value)
    if declared_type == "array":
        return to_array(value)
    return value


# Limpia los ausentes y convierte los tipos, antes de validar lo que falta.
def normalize_arguments(
    tool: str, properties: dict[str, Any], arguments: dict[str, Any]
) -> dict[str, Any]:
    """Normaliza los argumentos de una invocación contra el esquema.

    Args:
        tool: Nombre de la herramienta.
        properties: Los parámetros declarados, como están en el esquema que
            recibió el modelo.
        arguments: Los argumentos tal como los mandó.

    Returns:
        Los argumentos sin los ausentes y con los numéricos convertidos. Si
        después de esto falta un obligatorio, eso ya lo decide quien valida.

    Raises:
        ToolArgumentError: Si un argumento numérico no se puede convertir.
    """
    normalized: dict[str, Any] = {}
    for parameter, value in arguments.items():
        if is_absent(value):
            continue
        declared = properties.get(parameter, {}).get("type")
        normalized[parameter] = coerce(tool, parameter, declared, value)
    return normalized
