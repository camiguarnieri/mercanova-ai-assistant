"""Definiciones de las herramientas, en el formato de tool calling de Ollama.

Esto es lo único de las herramientas que viaja al modelo, así que las
descripciones están escritas para que las lea él. La implementación está en
`tools.py`: acá no se consulta nada.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SEARCH_PRODUCTS = "search_products"
GET_PRODUCT_DETAILS = "get_product_details"
CHECK_AVAILABILITY = "check_availability"
COMPARE_PRODUCTS = "compare_products"
GET_RELATED_PRODUCTS = "get_related_products"

# Texto que se repite en los parámetros que esperan un identificador.
PRODUCT_ID_DESCRIPTION = (
    "Identificador del producto, como 'MN-MON-0001'. Tiene que venir de un resultado "
    "de search_products o de otra herramienta: no lo inventes."
)


# Arma la definición de una herramienta en el formato que espera Ollama.
def tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict:
    """Devuelve la definición de una herramienta.

    Args:
        name: Nombre con el que el modelo la invoca.
        description: Para qué sirve y cuándo usarla, escrito para el modelo.
        properties: Esquema JSON de cada parámetro.
        required: Nombres de los parámetros obligatorios.

    Returns:
        La definición lista para pasar en el argumento `tools` de `chat()`.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# Escribe los casos de uso de cada categoría, uno por línea.
def use_cases_by_category(grouped: Mapping[str, Sequence[str]]) -> str:
    """Arma el texto que le muestra al modelo qué caso de uso va con qué categoría.

    Args:
        grouped: `{categoría: casos de uso}`, de
            `catalog.list_use_cases_by_category()`.

    Returns:
        Una línea por categoría, o un texto vacío si no hay vocabulario.
    """
    if not grouped:
        return ""
    lines = "\n".join(
        f"{category}: {', '.join(use_cases)}" for category, use_cases in grouped.items()
    )
    return (
        " Cada categoría tiene los suyos, y hay que usar uno de los de la categoría "
        f"que estás buscando:\n{lines}"
    )


# Arma el esquema del parámetro de un filtro de valores cerrados.
def filter_parameter(description: str, values: Sequence[str]) -> dict[str, Any]:
    """Devuelve el esquema JSON de un filtro que solo acepta ciertos valores.

    La lista de valores va en `enum`, que es la forma en que el esquema dice
    "no hay otros". La descripción no la repite: lo único que agrega es lo que
    el `enum` no puede decir, como con qué categoría va cada caso de uso.

    Args:
        description: La descripción del parámetro, escrita para el modelo.
        values: Los valores válidos, sacados del catálogo. Si está vacía no se
            manda `enum`: es mejor no decir nada que listar valores que no
            sabemos si existen.

    Returns:
        El esquema del parámetro.
    """
    parameter: dict[str, Any] = {"type": "string", "description": description}
    if values:
        parameter["enum"] = list(values)
    return parameter


# Arma el esquema de search_products con el vocabulario real del catálogo.
def search_products_schema(
    categories: Sequence[str] = (), grouped_use_cases: Mapping[str, Sequence[str]] = {}
) -> dict[str, Any]:
    """Devuelve la definición de `search_products`.

    Las categorías van en el `enum` de `category`. Los casos de uso van en el
    `enum` de `recommended_for`, que es el que los valida, y además agrupados
    por categoría en su descripción, porque no todos existen en todas: pedir
    'video calls' en Headphones no trae nada aunque los dos valores existan.

    Args:
        categories: Las categorías del catálogo.
        grouped_use_cases: `{categoría: casos de uso}` del catálogo.

    Returns:
        La definición lista para pasar en el argumento `tools` de `chat()`.
    """
    use_cases = sorted(
        {use_case for use_cases in grouped_use_cases.values() for use_case in use_cases}
    )
    return tool(
        SEARCH_PRODUCTS,
        "Busca productos en el catálogo con filtros. Es la herramienta por la que se "
        "empieza cuando el usuario describe lo que necesita, y también para encontrar un "
        "producto del que sabés el nombre. Los valores de los filtros van en inglés, como "
        "están en el catálogo. De cada producto devuelve su precio y si tiene stock, pero "
        "no cuántas unidades: la cantidad se consulta con check_availability. Si no hay "
        "resultados lo dice y te devuelve los valores válidos de los filtros, para que "
        "corrijas y busques de nuevo.",
        {
            "category": filter_parameter(
                "Categoría del catálogo, en inglés. Solo una de las que enumera este "
                "parámetro, escrita igual.",
                categories,
            ),
            "brand": {
                "type": "string",
                "description": "Nombre de la marca, por ejemplo 'NovaTech'.",
            },
            "min_price": {
                "type": "number",
                "description": (
                    "Precio vigente mínimo, inclusive. Mandalo solo si el usuario dijo un "
                    "piso de precio. Si dijo un tope, como 'menos de 200', va únicamente "
                    "max_price. Nunca igual a max_price."
                ),
            },
            "max_price": {
                "type": "number",
                "description": (
                    "Precio vigente máximo, inclusive. Es el filtro para cuando el usuario "
                    "da un tope. Nunca igual a min_price."
                ),
            },
            "recommended_for": filter_parameter(
                "Caso de uso para el que el catálogo recomienda el producto, en inglés, "
                "escrito igual. Es el filtro para cuando el usuario dice para qué lo va a "
                "usar; si ninguno encaja con lo que dijo, omití el parámetro."
                + use_cases_by_category(grouped_use_cases),
                use_cases,
            ),
            "search": {
                "type": "string",
                "description": (
                    "Nombre de producto o de marca a buscar, en inglés y como está en el "
                    "catálogo, por ejemplo 'Nova Vision' o '4K'. No es para describir la "
                    "necesidad del usuario: para eso están category y recommended_for, y si "
                    "ya los usás, omití este parámetro."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Cuántos productos devolver, de 1 a 20. Por defecto 5.",
            },
        },
        [],
    )


SEARCH_PRODUCTS_SCHEMA = search_products_schema()

GET_PRODUCT_DETAILS_SCHEMA = tool(
    GET_PRODUCT_DETAILS,
    "Trae la ficha completa de un producto: descripción, precio, si hay stock, datos de "
    "garantía y todas sus especificaciones técnicas. No trae la cantidad de unidades, "
    "que se consulta con check_availability. Usala cuando el usuario pregunta por un "
    "producto concreto o necesitás una especificación para responder.",
    {"product_id": {"type": "string", "description": PRODUCT_ID_DESCRIPTION}},
    ["product_id"],
)

CHECK_AVAILABILITY_SCHEMA = tool(
    CHECK_AVAILABILITY,
    "Consulta el stock actual de un producto, sumando los depósitos. Es la única "
    "herramienta que devuelve una cantidad de unidades: las demás solo dicen si hay "
    "stock o no. Usala siempre antes de afirmar un número o que un producto está "
    "disponible, incluso si ya lo consultaste antes en esta conversación.",
    {"product_id": {"type": "string", "description": PRODUCT_ID_DESCRIPTION}},
    ["product_id"],
)

COMPARE_PRODUCTS_SCHEMA = tool(
    COMPARE_PRODUCTS,
    "Compara dos o tres productos y devuelve sus datos enfrentados: precio, si hay "
    "stock, marca, puntaje, garantía y las especificaciones que tienen en común. Es la "
    "forma de contestar cuál es mejor en una característica. Usala cuando el usuario "
    "duda entre productos concretos, y también cuando pregunta cuál de los que le "
    "mostraste es mejor en algo.",
    {
        "product_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Dos o tres identificadores de producto, que tienen que venir de "
                "resultados anteriores de otras herramientas. Los elegís vos: son "
                "internos y no se le preguntan al usuario. Si mandás más de tres, "
                "compara los tres primeros y te dice cuáles quedaron afuera."
            ),
        }
    },
    ["product_ids"],
)

GET_RELATED_PRODUCTS_SCHEMA = tool(
    GET_RELATED_PRODUCTS,
    "Trae los productos que el catálogo relaciona con uno dado. Usala para ofrecer "
    "alternativas cuando algo no tiene stock o no convence, y para sugerir accesorios "
    "una vez que el usuario eligió un producto.",
    {
        "product_id": {"type": "string", "description": PRODUCT_ID_DESCRIPTION},
        "relation_type": {
            "type": "string",
            "enum": ["alternative_to", "accessory_for", "often_bought_with"],
            "description": (
                "Tipo de relación: 'alternative_to' para alternativas al producto, "
                "'accessory_for' para accesorios, 'often_bought_with' para lo que se "
                "suele comprar junto. Si no lo pasás, devuelve los tres tipos."
            ),
        },
    },
    ["product_id"],
)

# Arma las cinco definiciones con el vocabulario que tenga el catálogo.
def build_tool_schemas(
    categories: Sequence[str] = (),
    grouped_use_cases: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    """Devuelve las herramientas que se le presentan al modelo.

    Args:
        categories: Las categorías del catálogo, de `catalog.list_category_names()`.
        grouped_use_cases: Los casos de uso por categoría, de
            `catalog.list_use_cases_by_category()`.

    Returns:
        Las cinco definiciones, en el orden en que las lee el modelo. Sin
        vocabulario devuelve las mismas herramientas sin las listas de valores:
        el asistente sigue funcionando, solo con menos ayuda.
    """
    return [
        search_products_schema(categories, grouped_use_cases or {}),
        GET_PRODUCT_DETAILS_SCHEMA,
        CHECK_AVAILABILITY_SCHEMA,
        COMPARE_PRODUCTS_SCHEMA,
        GET_RELATED_PRODUCTS_SCHEMA,
    ]


# Las herramientas sin el vocabulario del catálogo. La validación de los
# argumentos usa estas, porque los parámetros son siempre los mismos; lo que
# viaja al modelo lo arma `vocabulary.py` con los valores de la base.
TOOL_SCHEMAS: list[dict[str, Any]] = build_tool_schemas()

TOOL_NAMES: tuple[str, ...] = tuple(schema["function"]["name"] for schema in TOOL_SCHEMAS)
