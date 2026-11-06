"""Las seis funciones que el LLM puede invocar, sobre `catalog.py`.

Cada herramienta devuelve datos reales de la base o dice explícitamente que no
encontró nada. Ninguna completa un valor por defecto ni adivina: si el dato no
está, la respuesta lo dice y el modelo tiene que decírselo al usuario.

La validación de los argumentos y el ruteo por nombre están en
`tool_router.py`; acá cada función se invoca con sus parámetros ya válidos.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend import catalog

# Cuántos productos devuelve una búsqueda si el modelo no pide otra cosa.
DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 20

MIN_COMPARE = 2
MAX_COMPARE = 3


class ToolError(RuntimeError):
    """Error de la capa de herramientas."""


class UnknownToolError(ToolError):
    """El modelo pidió una herramienta que no existe."""


class ToolArgumentError(ToolError):
    """Los argumentos con los que el modelo invocó la herramienta no sirven."""


# Busca productos con los filtros que armó el modelo.
def search_products(
    connection: sqlite3.Connection,
    category: str | None = None,
    brand: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    recommended_for: str | None = None,
    search: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict[str, Any]:
    """Busca productos en el catálogo.

    Args:
        connection: Conexión abierta con `db.connect()`.
        category: Categoría exacta, en inglés.
        brand: Nombre o identificador de la marca.
        min_price: Precio vigente mínimo, inclusive.
        max_price: Precio vigente máximo, inclusive.
        recommended_for: Caso de uso, en inglés.
        search: Texto libre, en inglés.
        limit: Cuántos productos devolver. Se acota a `MAX_SEARCH_LIMIT`.

    Returns:
        Los productos encontrados y el total sin paginar. Si no hay ninguno,
        `found` es `False` y el mensaje lo aclara.
    """
    page = catalog.list_products(
        connection,
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        recommended_for=recommended_for,
        search=search,
        limit=max(1, min(int(limit), MAX_SEARCH_LIMIT)),
    )
    if not page.items:
        return {
            "found": False,
            "total": 0,
            "products": [],
            "message": (
                "No hay productos en el catálogo que cumplan esos filtros. "
                "Probá con menos filtros, otra categoría o un rango de precio más amplio."
            ),
        }
    return {
        "found": True,
        "total": page.total,
        "returned": len(page.items),
        "products": [item.model_dump(mode="json") for item in page.items],
    }


# Trae la ficha completa de un producto.
def get_product_details(connection: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    """Busca un producto por su identificador.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto.

    Returns:
        La ficha completa del producto.

    Raises:
        catalog.ProductNotFoundError: Si el producto no existe. `run_tool` la
            traduce a un resultado con `error` para que lo lea el modelo.
    """
    detail = catalog.get_product(connection, product_id)
    return {"found": True, "product": detail.model_dump(mode="json")}


# Consulta el stock actual del producto, sumando los depósitos.
def check_availability(connection: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    """Consulta la disponibilidad de un producto.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto.

    Returns:
        Las unidades disponibles y si hay stock. No estima: el número sale de
        sumar el inventario de los depósitos en este momento.

    Raises:
        catalog.ProductNotFoundError: Si el producto no existe.
    """
    detail = catalog.get_product(connection, product_id)
    available = detail.available_qty
    return {
        "found": True,
        "product_id": detail.product_id,
        "name": detail.name,
        "available_qty": available,
        "in_stock": available > 0,
        "active": detail.active,
        "message": (
            f"Hay {available} unidades disponibles."
            if available > 0
            else "No hay stock disponible de este producto en ningún depósito."
        ),
    }


# Enfrenta los datos de dos o tres productos.
def compare_products(
    connection: sqlite3.Connection, product_ids: list[str]
) -> dict[str, Any]:
    """Compara productos entre sí.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_ids: Entre `MIN_COMPARE` y `MAX_COMPARE` identificadores.

    Returns:
        Los datos comparables de cada producto y las especificaciones que
        tienen en común, con el valor de cada uno tal como está en el catálogo.

    Raises:
        ToolArgumentError: Si la cantidad de identificadores no sirve.
        catalog.ProductNotFoundError: Si alguno no existe.
    """
    if not isinstance(product_ids, list) or not MIN_COMPARE <= len(product_ids) <= MAX_COMPARE:
        raise ToolArgumentError(
            f"compare_products necesita entre {MIN_COMPARE} y {MAX_COMPARE} "
            f"identificadores de producto. Llegaron: {product_ids!r}."
        )

    details = [catalog.get_product(connection, product_id) for product_id in product_ids]
    products = [
        {
            "product_id": detail.product_id,
            "name": detail.name,
            "brand": detail.brand,
            "category": detail.category,
            "subcategory": detail.subcategory,
            "currency": detail.currency,
            "current_price": detail.current_price,
            "available_qty": detail.available_qty,
            "rating": detail.rating,
            "warranty_months": detail.warranty_months,
            "recommended_for": detail.recommended_for,
            "not_recommended_for": detail.not_recommended_for,
        }
        for detail in details
    ]

    # Solo se comparan los atributos que tienen todos, para no enfrentar huecos.
    by_product = [
        {
            (specification.attribute_group, specification.attribute_name): specification
            for specification in detail.specifications
        }
        for detail in details
    ]
    shared = set(by_product[0])
    for attributes in by_product[1:]:
        shared &= set(attributes)

    specifications = [
        {
            "attribute_group": group,
            "attribute_name": name,
            "values": {
                detail.product_id: attributes[(group, name)].model_dump(
                    mode="json", include={"value_text", "value_number", "unit"}
                )
                for detail, attributes in zip(details, by_product)
            },
        }
        for group, name in sorted(shared)
    ]
    return {"found": True, "products": products, "shared_specifications": specifications}


# Trae los productos que el catálogo relaciona con uno dado.
def get_related_products(
    connection: sqlite3.Connection, product_id: str, relation_type: str | None = None
) -> dict[str, Any]:
    """Busca alternativas, accesorios o productos que se compran juntos.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto del que se parte.
        relation_type: Tipo de relación, o `None` para los tres.

    Returns:
        Los relacionados, del más fuerte al más débil. Si el producto existe
        pero no tiene relaciones cargadas, `found` es `False` y lo aclara.
    """
    related = catalog.list_related_products(connection, product_id, relation_type)
    if not related:
        kind = f" del tipo '{relation_type}'" if relation_type else ""
        return {
            "found": False,
            "related": [],
            "message": (
                f"El catálogo no tiene productos relacionados{kind} para '{product_id}'."
            ),
        }
    return {
        "found": True,
        "count": len(related),
        "related": [item.model_dump(mode="json") for item in related],
    }


# Lista las categorías del catálogo, agrupadas con sus subcategorías.
def list_categories(connection: sqlite3.Connection) -> dict[str, Any]:
    """Lista las categorías disponibles.

    Args:
        connection: Conexión abierta con `db.connect()`.

    Returns:
        Cada categoría con sus subcategorías, para que el modelo filtre con un
        nombre que existe en vez de adivinarlo.
    """
    grouped: dict[str, list[str]] = {}
    for category in catalog.list_categories(connection):
        grouped.setdefault(category.category_name, []).append(category.subcategory_name)
    return {
        "found": bool(grouped),
        "categories": [
            {"category": name, "subcategories": subcategories}
            for name, subcategories in grouped.items()
        ],
    }


