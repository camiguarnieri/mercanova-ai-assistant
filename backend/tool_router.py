"""Validación y ruteo de las herramientas que pide el modelo.

Decide si la invocación sirve y a qué función va. No consulta el catálogo: eso
es de `tools.py`, y acá solo se la llama.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any

from backend import cart, cart_tools, catalog, provenance, tool_arguments, tool_schemas, tools
from backend.carts import CartSession

# Qué función implementa cada herramienta del esquema. Las dos del carrito
# reciben además el carrito de la sesión, que no es un argumento del modelo.
IMPLEMENTATIONS = {
    tool_schemas.SEARCH_PRODUCTS: tools.search_products,
    tool_schemas.GET_PRODUCT_DETAILS: tools.get_product_details,
    tool_schemas.CHECK_AVAILABILITY: tools.check_availability,
    tool_schemas.COMPARE_PRODUCTS: tools.compare_products,
    tool_schemas.GET_RELATED_PRODUCTS: tools.get_related_products,
    tool_schemas.ADD_TO_CART: cart_tools.add_to_cart,
    tool_schemas.REMOVE_FROM_CART: cart_tools.remove_from_cart,
}

# Los parámetros declarados de cada herramienta, para validar contra el mismo
# esquema que recibió el modelo y no contra una copia.
SCHEMA_BY_NAME = {
    schema["function"]["name"]: schema["function"]["parameters"]
    for schema in tool_schemas.TOOL_SCHEMAS
}


# Valida los argumentos contra el esquema que recibió el modelo.
def validate_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Revisa los argumentos de una invocación y los limpia.

    Args:
        name: Nombre de la herramienta.
        arguments: Argumentos tal como los mandó el modelo.

    Primero se normaliza lo que mandó el modelo —se tiran los ausentes y se
    convierten los números que vinieron como texto— y recién después se exige
    lo obligatorio: un 'null' en un parámetro opcional no es un error, es la
    manera en que un modelo chico dice que no lo usa.

    Returns:
        Los argumentos listos para invocar la herramienta.

    Raises:
        tools.UnknownToolError: Si la herramienta no existe.
        tools.ToolArgumentError: Si sobra un argumento, falta uno obligatorio o
            uno numérico no se puede convertir.
    """
    if name not in SCHEMA_BY_NAME:
        raise tools.UnknownToolError(
            f"Volvé a intentar con una de las herramientas que existen: "
            f"{', '.join(tool_schemas.TOOL_NAMES)}. '{name}' no es ninguna de esas."
        )

    schema = SCHEMA_BY_NAME[name]
    unknown = sorted(set(arguments) - set(schema["properties"]))
    if unknown:
        allowed = ", ".join(schema["properties"])
        raise tools.ToolArgumentError(
            f"Volvé a invocar '{name}' sin el argumento {unknown[0]!r}, que no existe. "
            f"Los que acepta son: {allowed}."
        )

    cleaned = tool_arguments.normalize_arguments(name, schema["properties"], arguments)
    missing = [parameter for parameter in schema["required"] if parameter not in cleaned]
    if missing:
        raise tools.ToolArgumentError(
            f"Volvé a invocar '{name}' con el argumento '{missing[0]}', que es "
            f"obligatorio y no llegó."
        )
    return cleaned


# Devuelve los argumentos como quedaron, para poder mostrarlos en la interfaz.
def arguments_for_trace(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Normaliza los argumentos de una invocación solo para mostrarlos.

    La interfaz muestra con qué se consultó el catálogo, así que conviene
    mostrar los argumentos con los que se corrió la herramienta y no los
    'null' que el modelo manda de más. Si no se pueden validar, se devuelven
    tal como llegaron: la traza tiene que mostrar lo que pasó, no una versión
    prolija de lo que pasó.

    Args:
        name: Nombre de la herramienta que pidió el modelo.
        arguments: Argumentos de la invocación.

    Returns:
        Los argumentos normalizados, o los originales si la validación falla.
    """
    try:
        return validate_arguments(name, arguments)
    except tools.ToolError:
        return dict(arguments)


# Ejecuta la herramienta que pidió el modelo y nunca lo deja sin respuesta.
def run_tool(
    connection: sqlite3.Connection,
    name: str,
    arguments: dict[str, Any],
    known_products: Iterable[str] | None = None,
    cart_session: CartSession | None = None,
) -> dict[str, Any]:
    """Corre una herramienta por nombre.

    Los errores no se propagan: se devuelven como resultado para que el modelo
    los lea, se corrija y la conversación siga. El mensaje dice qué hacer.

    Args:
        connection: Conexión abierta con `db.connect()`.
        name: Nombre de la herramienta que pidió el modelo.
        arguments: Argumentos de la invocación.
        known_products: Los product_id que aparecieron en resultados de esta
            conversación. Si se pasan, un identificador que no esté entre
            ellos no se ejecuta: el modelo lo inventó. Si es `None` no se
            revisa la procedencia, que es lo que hace falta para probar una
            herramienta sola.
        cart_session: El carrito de esta conversación. Las herramientas que lo
            escriben lo reciben como primer argumento, y el modelo no puede
            elegirlo: lo pone el servidor. Si es `None`, esas herramientas no
            se ejecutan y devuelven un error en vez de tocar otro carrito.

    Returns:
        El resultado de la herramienta, o un diccionario con `error` explicando
        qué salió mal.
    """
    try:
        cleaned = validate_arguments(name, arguments)
        if known_products is not None:
            provenance.check_ids(cleaned, known_products)
        if name in tool_schemas.CART_TOOL_NAMES:
            if cart_session is None:
                raise tools.ToolError(
                    f"No uses '{name}' acá: esta consulta no tiene un carrito asociado. "
                    f"Contestá con las herramientas que leen el catálogo."
                )
            return IMPLEMENTATIONS[name](connection, cart_session, **cleaned)
        return IMPLEMENTATIONS[name](connection, **cleaned)
    except (tools.ToolError, catalog.CatalogError, cart.CartError) as error:
        return {"found": False, "error": str(error)}
    except TypeError as error:
        return {
            "found": False,
            "error": f"La herramienta '{name}' se invocó mal: {error}.",
        }
    except sqlite3.Error as error:
        return {
            "found": False,
            "error": (
                f"No se pudo consultar el catálogo. Si la base no está cargada, "
                f"corré: python scripts/load_dataset.py. Detalle: {error}"
            ),
        }
