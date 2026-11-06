"""Validación y ruteo de las herramientas que pide el modelo.

Decide si la invocación sirve y a qué función va. No consulta el catálogo: eso
es de `tools.py`, y acá solo se la llama.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend import catalog, tool_schemas, tools

# Qué función implementa cada herramienta del esquema.
IMPLEMENTATIONS = {
    tool_schemas.SEARCH_PRODUCTS: tools.search_products,
    tool_schemas.GET_PRODUCT_DETAILS: tools.get_product_details,
    tool_schemas.CHECK_AVAILABILITY: tools.check_availability,
    tool_schemas.COMPARE_PRODUCTS: tools.compare_products,
    tool_schemas.GET_RELATED_PRODUCTS: tools.get_related_products,
    tool_schemas.LIST_CATEGORIES: tools.list_categories,
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

    Returns:
        Los argumentos sin los vacíos, que el modelo suele mandar igual.

    Raises:
        tools.UnknownToolError: Si la herramienta no existe.
        tools.ToolArgumentError: Si sobra o falta un argumento.
    """
    if name not in SCHEMA_BY_NAME:
        raise tools.UnknownToolError(
            f"La herramienta '{name}' no existe. "
            f"Las disponibles son: {', '.join(tool_schemas.TOOL_NAMES)}."
        )

    schema = SCHEMA_BY_NAME[name]
    unknown = sorted(set(arguments) - set(schema["properties"]))
    if unknown:
        allowed = ", ".join(schema["properties"]) or "ninguno"
        raise tools.ToolArgumentError(
            f"La herramienta '{name}' no acepta el argumento {unknown[0]!r}. "
            f"Los que acepta son: {allowed}."
        )

    cleaned = {
        key: value for key, value in arguments.items() if value is not None and value != ""
    }
    missing = [parameter for parameter in schema["required"] if parameter not in cleaned]
    if missing:
        raise tools.ToolArgumentError(
            f"La herramienta '{name}' necesita el argumento '{missing[0]}' y no llegó."
        )
    return cleaned


# Ejecuta la herramienta que pidió el modelo y nunca lo deja sin respuesta.
def run_tool(
    connection: sqlite3.Connection, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Corre una herramienta por nombre.

    Los errores no se propagan: se devuelven como resultado para que el modelo
    los lea, se corrija y la conversación siga. El mensaje dice qué hacer.

    Args:
        connection: Conexión abierta con `db.connect()`.
        name: Nombre de la herramienta que pidió el modelo.
        arguments: Argumentos de la invocación.

    Returns:
        El resultado de la herramienta, o un diccionario con `error` explicando
        qué salió mal.
    """
    try:
        cleaned = validate_arguments(name, arguments)
        return IMPLEMENTATIONS[name](connection, **cleaned)
    except (tools.ToolError, catalog.CatalogError) as error:
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
