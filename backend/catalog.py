"""Consultas del catálogo contra SQLite.

Devuelve modelos Pydantic y no sabe nada de FastAPI. Todo lo que afirma sale de
una consulta: si un dato no está en la base, el modelo lo devuelve en null. El
SQL está en `catalog_sql.py`.
"""

from __future__ import annotations

import sqlite3

from backend import catalog_sql
from backend.models import (
    Brand,
    Category,
    Product,
    ProductDetail,
    ProductPage,
    RelatedProduct,
    Specification,
)

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class CatalogError(RuntimeError):
    """Error de la capa de catálogo."""


class ProductNotFoundError(CatalogError):
    """El producto pedido no existe en el catálogo."""


class InvalidFilterError(CatalogError):
    """Los filtros de búsqueda no son válidos."""


# Valida el paginado y el rango de precios antes de consultar.
def check_query(limit: int, offset: int, min_price: float | None, max_price: float | None) -> None:
    """Verifica los parámetros del listado.

    Args:
        limit: Cantidad máxima de productos a devolver.
        offset: Cantidad de productos a saltear.
        min_price: Precio vigente mínimo, inclusive.
        max_price: Precio vigente máximo, inclusive.

    Raises:
        InvalidFilterError: Si el paginado o los precios no sirven.
    """
    if not 1 <= limit <= MAX_LIMIT:
        raise InvalidFilterError(
            f"El parámetro 'limit' tiene que estar entre 1 y {MAX_LIMIT}. Llegó: {limit}."
        )
    if offset < 0:
        raise InvalidFilterError(f"El parámetro 'offset' no puede ser negativo: {offset}.")
    for label, price in (("min_price", min_price), ("max_price", max_price)):
        if price is not None and price < 0:
            raise InvalidFilterError(f"El filtro '{label}' no puede ser negativo: {price}.")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise InvalidFilterError(
            f"El precio mínimo ({min_price}) no puede ser mayor que el máximo ({max_price})."
        )


# Lista productos del catálogo con filtros opcionales y paginado.
def list_products(
    connection: sqlite3.Connection,
    *,
    category: str | None = None,
    subcategory: str | None = None,
    brand: str | None = None,
    recommended_for: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    search: str | None = None,
    only_active: bool = True,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> ProductPage:
    """Busca productos en el catálogo.

    Args:
        connection: Conexión abierta con `db.connect()`.
        category: Nombre de la categoría por la que filtrar.
        subcategory: Nombre de la subcategoría por la que filtrar.
        brand: Nombre o identificador de la marca.
        recommended_for: Uso para el que el catálogo recomienda el producto,
            por ejemplo `'office work'`. Sirve para las consultas por caso de
            uso y compara por substring, sin distinguir mayúsculas.
        min_price: Precio vigente mínimo, inclusive. Deja afuera los productos
            sin precio cargado, porque no se puede afirmar que entren.
        max_price: Precio vigente máximo, inclusive.
        search: Texto libre a buscar en el nombre, las descripciones,
            `recommended_for` y `tags`.
        only_active: Si es `True`, deja afuera los productos dados de baja.
        limit: Cantidad máxima de productos a devolver, de 1 a `MAX_LIMIT`.
        offset: Cantidad de productos a saltear.

    Returns:
        La página de resultados, con el total sin paginar.

    Raises:
        InvalidFilterError: Si los filtros o el paginado no son válidos.
    """
    check_query(limit, offset, min_price, max_price)
    where, parameters = catalog_sql.build_filters(
        category=category,
        subcategory=subcategory,
        brand=brand,
        recommended_for=recommended_for,
        min_price=min_price,
        max_price=max_price,
        search=search,
        only_active=only_active,
    )

    total = int(
        connection.execute(
            f"SELECT COUNT(*) AS total {catalog_sql.PRODUCT_SOURCE} {where}", parameters
        ).fetchone()["total"]
    )
    rows = connection.execute(
        f"SELECT {catalog_sql.SUMMARY_COLUMNS} {catalog_sql.PRODUCT_SOURCE} {where} "
        f"{catalog_sql.PRODUCT_ORDER} LIMIT ? OFFSET ?",
        [*parameters, limit, offset],
    ).fetchall()

    items = [Product.model_validate(dict(row)) for row in rows]
    return ProductPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


# Trae la ficha completa de un producto, con precio, stock y especificaciones.
def get_product(connection: sqlite3.Connection, product_id: str) -> ProductDetail:
    """Busca un producto por su identificador.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto, por ejemplo `'MN-MON-0001'`.

    Returns:
        La ficha del producto, con sus especificaciones ordenadas.

    Raises:
        ProductNotFoundError: Si el identificador no existe en el catálogo.
    """
    row = connection.execute(
        f"SELECT {catalog_sql.SUMMARY_COLUMNS} {catalog_sql.DETAIL_COLUMNS} "
        f"{catalog_sql.PRODUCT_SOURCE} WHERE p.product_id = ?",
        [product_id.strip()],
    ).fetchone()
    if row is None:
        raise ProductNotFoundError(
            f"No existe el producto '{product_id}' en el catálogo. "
            f"Buscá el identificador correcto con el listado de productos."
        )

    specifications = connection.execute(
        catalog_sql.SPECIFICATIONS_QUERY, [row["product_id"]]
    ).fetchall()

    detail = dict(row)
    # Los valores de texto se guardan tal cual: 'None' significa que el producto
    # no tiene esa característica, y no es lo mismo que no tener el dato.
    detail["specifications"] = [
        Specification.model_validate(dict(specification)) for specification in specifications
    ]
    return ProductDetail.model_validate(detail)


# Lista los productos que el catálogo relaciona con uno dado.
def list_related_products(
    connection: sqlite3.Connection, product_id: str, relation_type: str | None = None
) -> list[RelatedProduct]:
    """Busca los productos relacionados con uno dado.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto del que se parte.
        relation_type: Tipo de relación por el que filtrar. Si es `None`, trae
            los tres tipos juntos.

    Returns:
        Los relacionados, del más fuerte al más débil. Una lista vacía
        significa que el producto existe pero no tiene relaciones cargadas.

    Raises:
        ProductNotFoundError: Si el producto del que se parte no existe.
        InvalidFilterError: Si el tipo de relación no es uno de los del dataset.
    """
    identifier = product_id.strip()
    if relation_type is not None and relation_type not in catalog_sql.RELATION_TYPES:
        raise InvalidFilterError(
            f"El tipo de relación '{relation_type}' no existe. "
            f"Los válidos son: {', '.join(catalog_sql.RELATION_TYPES)}."
        )
    if connection.execute(catalog_sql.PRODUCT_EXISTS_QUERY, [identifier]).fetchone() is None:
        raise ProductNotFoundError(
            f"No existe el producto '{product_id}' en el catálogo. "
            f"Buscá el identificador correcto con el listado de productos."
        )

    where = "WHERE r.product_id = ?"
    parameters: list[object] = [identifier]
    if relation_type is not None:
        where += " AND r.relation_type = ?"
        parameters.append(relation_type)

    rows = connection.execute(
        f"SELECT r.relation_type, r.strength, {catalog_sql.SUMMARY_COLUMNS} "
        f"{catalog_sql.RELATED_SOURCE} {where} {catalog_sql.RELATED_ORDER}",
        parameters,
    ).fetchall()

    related: list[RelatedProduct] = []
    for row in rows:
        fields = dict(row)
        relation = {
            "relation_type": fields.pop("relation_type"),
            "strength": fields.pop("strength"),
            "product": Product.model_validate(fields),
        }
        related.append(RelatedProduct.model_validate(relation))
    return related


# Lista los pares categoría/subcategoría del catálogo.
def list_categories(connection: sqlite3.Connection) -> list[Category]:
    """Devuelve todas las categorías con sus subcategorías.

    Args:
        connection: Conexión abierta con `db.connect()`.

    Returns:
        Los pares categoría/subcategoría, ordenados para mostrar.
    """
    rows = connection.execute(catalog_sql.CATEGORIES_QUERY).fetchall()
    return [Category.model_validate(dict(row)) for row in rows]


# Lista las marcas del catálogo.
def list_brands(connection: sqlite3.Connection) -> list[Brand]:
    """Devuelve todas las marcas.

    Args:
        connection: Conexión abierta con `db.connect()`.

    Returns:
        Las marcas, ordenadas por nombre.
    """
    rows = connection.execute(catalog_sql.BRANDS_QUERY).fetchall()
    return [Brand.model_validate(dict(row)) for row in rows]
