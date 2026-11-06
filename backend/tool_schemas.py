"""Definiciones de las herramientas, en el formato de tool calling de Ollama.

Esto es lo único de las herramientas que viaja al modelo, así que las
descripciones están escritas para que las lea él. La implementación está en
`tools.py`: acá no se consulta nada.
"""

from __future__ import annotations

from typing import Any

SEARCH_PRODUCTS = "search_products"
GET_PRODUCT_DETAILS = "get_product_details"
CHECK_AVAILABILITY = "check_availability"
COMPARE_PRODUCTS = "compare_products"
GET_RELATED_PRODUCTS = "get_related_products"
LIST_CATEGORIES = "list_categories"

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


SEARCH_PRODUCTS_SCHEMA = tool(
    SEARCH_PRODUCTS,
    "Busca productos en el catálogo con filtros. Es la herramienta por la que se "
    "empieza cuando el usuario describe lo que necesita. Los valores de los filtros van "
    "en inglés, como están en el catálogo. Devuelve un resumen de cada producto con su "
    "precio y su stock. Si no hay resultados lo dice explícitamente.",
    {
        "category": {
            "type": "string",
            "description": (
                "Categoría exacta del catálogo, en inglés, por ejemplo 'Monitors' o "
                "'Headphones'. Si no sabés qué categorías hay, usá list_categories."
            ),
        },
        "brand": {
            "type": "string",
            "description": "Nombre de la marca, por ejemplo 'NovaTech'.",
        },
        "min_price": {
            "type": "number",
            "description": "Precio vigente mínimo, inclusive, en la moneda del catálogo.",
        },
        "max_price": {
            "type": "number",
            "description": "Precio vigente máximo, inclusive. Útil cuando el usuario da un tope.",
        },
        "recommended_for": {
            "type": "string",
            "description": (
                "Caso de uso para el que el catálogo recomienda el producto, en inglés: "
                "'office work', 'programming', 'gaming', 'content creation', 'travel', "
                "'video editing' y otros. Es el filtro para cuando el usuario dice para "
                "qué lo va a usar."
            ),
        },
        "search": {
            "type": "string",
            "description": (
                "Texto libre, en inglés. Busca en el nombre, las descripciones, el caso "
                "de uso y las etiquetas. Usalo para características que no son un filtro, "
                "como '4K' o 'noise-cancelling'."
            ),
        },
        "limit": {
            "type": "integer",
            "description": "Cuántos productos devolver, de 1 a 20. Por defecto 5.",
        },
    },
    [],
)

GET_PRODUCT_DETAILS_SCHEMA = tool(
    GET_PRODUCT_DETAILS,
    "Trae la ficha completa de un producto: descripción, precio, stock total, datos de "
    "garantía y todas sus especificaciones técnicas. Usala cuando el usuario pregunta "
    "por un producto concreto o necesitás una especificación para responder.",
    {"product_id": {"type": "string", "description": PRODUCT_ID_DESCRIPTION}},
    ["product_id"],
)

CHECK_AVAILABILITY_SCHEMA = tool(
    CHECK_AVAILABILITY,
    "Consulta el stock actual de un producto, sumando los depósitos. Usala siempre "
    "antes de afirmar que un producto está disponible, incluso si ya lo consultaste "
    "antes en esta conversación.",
    {"product_id": {"type": "string", "description": PRODUCT_ID_DESCRIPTION}},
    ["product_id"],
)

COMPARE_PRODUCTS_SCHEMA = tool(
    COMPARE_PRODUCTS,
    "Compara dos o tres productos y devuelve sus datos enfrentados: precio, stock, "
    "marca, puntaje, garantía y las especificaciones que tienen en común. Usala cuando "
    "el usuario duda entre productos concretos.",
    {
        "product_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Dos o tres identificadores de producto, que tienen que venir de "
                "resultados anteriores de otras herramientas."
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

LIST_CATEGORIES_SCHEMA = tool(
    LIST_CATEGORIES,
    "Lista las categorías y subcategorías del catálogo, en inglés. Usala cuando no "
    "sabés con qué categoría buscar, antes de adivinar un nombre.",
    {},
    [],
)

# Las seis herramientas, en el orden en que se le presentan al modelo.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    SEARCH_PRODUCTS_SCHEMA,
    GET_PRODUCT_DETAILS_SCHEMA,
    CHECK_AVAILABILITY_SCHEMA,
    COMPARE_PRODUCTS_SCHEMA,
    GET_RELATED_PRODUCTS_SCHEMA,
    LIST_CATEGORIES_SCHEMA,
]

TOOL_NAMES: tuple[str, ...] = tuple(schema["function"]["name"] for schema in TOOL_SCHEMAS)
