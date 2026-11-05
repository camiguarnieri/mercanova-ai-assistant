"""El SQL del catálogo: columnas, joins y armado de los filtros.

Solo arma texto SQL y parámetros. No abre conexiones, no consulta y no valida
reglas de negocio: eso es de `catalog.py`.
"""

from __future__ import annotations

from typing import Any

# Columnas del resumen: los nombres coinciden con los campos de Product.
SUMMARY_COLUMNS = """
    p.product_id, p.sku, p.name, p.brand, p.category, p.subcategory,
    p.short_description, p.recommended_for, p.active,
    pr.currency, pr.current_price,
    COALESCE(stock.available_qty, 0) AS available_qty
"""

# Columnas que agrega la ficha completa, con los campos de ProductDetail.
DETAIL_COLUMNS = """,
    p.description, p.not_recommended_for, p.key_features, p.tags,
    p.color, p.weight_kg, p.warranty_months, p.return_days, p.rating,
    p.review_count, p.launch_date, p.image_url,
    pr.list_price, pr.discount_percent, pr.tax_included, pr.price_updated_at
"""

# El stock vive por depósito: para el catálogo se suma el de los 5 depósitos.
# Los LEFT JOIN evitan que un producto desaparezca del catálogo por no tener
# precio o inventario cargado; en ese caso el precio viaja en null.
PRODUCT_SOURCE = """
FROM products AS p
LEFT JOIN pricing AS pr ON pr.product_id = p.product_id
LEFT JOIN (
    SELECT product_id, SUM(available_qty) AS available_qty
    FROM inventory
    GROUP BY product_id
) AS stock ON stock.product_id = p.product_id
"""

# El orden por nombre e id hace que el paginado sea estable entre llamadas.
PRODUCT_ORDER = "ORDER BY p.name, p.product_id"

SPECIFICATIONS_QUERY = """
SELECT attribute_group, attribute_name, value_text, value_number, unit
FROM specifications
WHERE product_id = ?
ORDER BY attribute_group, attribute_name
"""

CATEGORIES_QUERY = """
SELECT category_id, category_name, subcategory_id, subcategory_name, department
FROM categories
ORDER BY category_name, subcategory_name
"""

BRANDS_QUERY = """
SELECT brand_id, brand_name, country_of_origin, positioning
FROM brands
ORDER BY brand_name
"""

# Campos que mira la búsqueda libre. recommended_for y tags son los que dicen
# para qué sirve cada producto, así que una consulta por caso de uso los pega
# aunque el nombre y la descripción no mencionen el uso.
SEARCH_FIELDS = (
    "p.name",
    "p.short_description",
    "p.description",
    "p.recommended_for",
    "p.tags",
)


# Arma el patrón de un LIKE escapando los comodines que escriba el usuario.
def like_pattern(text: str) -> str:
    """Convierte un texto de búsqueda en un patrón para `LIKE ... ESCAPE '\\'`.

    Args:
        text: Texto libre escrito por el usuario.

    Returns:
        El patrón con los comodines `%` y `_` escapados, para que un `%` suelto
        se busque como carácter y no traiga el catálogo entero.
    """
    escaped = text.strip().replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


# Traduce los filtros opcionales a condiciones SQL con parámetros.
def build_filters(
    category: str | None = None,
    subcategory: str | None = None,
    brand: str | None = None,
    recommended_for: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    search: str | None = None,
    only_active: bool = True,
) -> tuple[str, list[Any]]:
    """Arma la cláusula WHERE del listado de productos.

    Args:
        category: Nombre exacto de la categoría, sin distinguir mayúsculas.
        subcategory: Nombre exacto de la subcategoría.
        brand: Nombre o identificador de la marca.
        recommended_for: Uso buscado dentro de `recommended_for`, por ejemplo
            `'office work'`. Compara por substring, porque la columna trae
            varios usos separados por punto y coma.
        min_price: Precio vigente mínimo, inclusive.
        max_price: Precio vigente máximo, inclusive.
        search: Texto libre a buscar en el nombre, las descripciones,
            `recommended_for` y `tags`.
        only_active: Si es `True`, deja afuera los productos dados de baja.

    Returns:
        La cláusula WHERE y la lista de parámetros, en el orden en que van.
    """
    conditions: list[str] = []
    parameters: list[Any] = []
    if only_active:
        conditions.append("p.active = 1")
    if category:
        conditions.append("p.category = ? COLLATE NOCASE")
        parameters.append(category.strip())
    if subcategory:
        conditions.append("p.subcategory = ? COLLATE NOCASE")
        parameters.append(subcategory.strip())
    if brand:
        conditions.append("(p.brand = ? COLLATE NOCASE OR p.brand_id = ? COLLATE NOCASE)")
        parameters.extend([brand.strip(), brand.strip()])
    if recommended_for and recommended_for.strip():
        conditions.append("p.recommended_for LIKE ? ESCAPE '\\'")
        parameters.append(like_pattern(recommended_for))
    if min_price is not None:
        conditions.append("pr.current_price >= ?")
        parameters.append(min_price)
    if max_price is not None:
        conditions.append("pr.current_price <= ?")
        parameters.append(max_price)
    if search and search.strip():
        matches = " OR ".join(f"{field} LIKE ? ESCAPE '\\'" for field in SEARCH_FIELDS)
        conditions.append(f"({matches})")
        parameters.extend([like_pattern(search)] * len(SEARCH_FIELDS))

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, parameters
