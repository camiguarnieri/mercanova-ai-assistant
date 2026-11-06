"""Catálogo de prueba, chico y con los casos borde que importan.

Lo arma el test en una base temporal: ningún test lee la base real. Incluye un
producto sin precio cargado, uno sin inventario, uno dado de baja, uno sin stock
y una especificación con el texto literal "None".
"""

from __future__ import annotations

import sqlite3

BRANDS = [
    ("BR001", "NovaTech", "Uruguay", "balanced"),
    ("BR002", "Flux", "Brasil", "premium"),
]

CATEGORIES = [
    ("SUB001", "CAT01", "Monitors", "Office", "Electronics", 1),
    ("SUB002", "CAT01", "Monitors", "Gaming", "Electronics", 2),
    ("SUB003", "CAT02", "Headphones", "Gaming", "Audio", 3),
]

WAREHOUSES = [
    ("WH-A", "MercaNova Centro", "Montevideo", "Montevideo", "Uruguay", 1, 1),
    ("WH-B", "MercaNova Norte", "Salto", "Salto", "Uruguay", 0, 1),
]


# Arma la fila de un producto completando los campos que el test no usa.
def product(
    product_id: str,
    sku: str,
    name: str,
    brand: str,
    brand_id: str,
    category: str,
    subcategory: str,
    description: str,
    active: int,
    recommended_for: str,
    tags: str,
) -> tuple[object, ...]:
    """Devuelve una fila de `products` lista para insertar."""
    return (
        product_id,
        sku,
        name,
        brand,
        brand_id,
        category,
        subcategory,
        f"{name}, resumen de una línea.",
        description,
        recommended_for,
        None,
        "24-inch; IPS",
        tags,
        "Black",
        6.5,
        50.0,
        32.0,
        20.0,
        12,
        30,
        4.3,
        100,
        "2026-03-05",
        active,
        f"https://placehold.co/800x600/png?text={sku}",
    )


# Los casos de uso de recommended_for y tags no se repiten entre productos, y
# no aparecen en el nombre ni en la descripción: así un test que busca
# "programming" solo puede pasar si la búsqueda mira esos campos.
PRODUCTS = [
    product(
        "MN-MON-0001",
        "MON-10000",
        "Nova Vision 24",
        "NovaTech",
        "BR001",
        "Monitors",
        "Office",
        "Monitor IPS de 24 pulgadas para oficina.",
        1,
        "office work; programming",
        "monitor; display; qhd",
    ),
    product(
        "MN-MON-0002",
        "MON-10001",
        "Flux Vision 27",
        "Flux",
        "BR002",
        "Monitors",
        "Gaming",
        "Monitor de 27 pulgadas y 240 Hz para jugar.",
        1,
        "gaming; content creation",
        "monitor; high-refresh",
    ),
    product(
        "MN-HDP-0001",
        "HDP-10000",
        "Nova Sound Pro",
        "NovaTech",
        "BR001",
        "Headphones",
        "Gaming",
        "Auriculares con cancelación de ruido.",
        1,
        "travel; office work",
        "headphones; noise-cancelling",
    ),
    # Dado de baja: no tiene que aparecer en el listado por defecto.
    product(
        "MN-HDP-0002",
        "HDP-10001",
        "Flux Buds",
        "Flux",
        "BR002",
        "Headphones",
        "Gaming",
        "Auriculares in-ear discontinuados.",
        0,
        "gaming; programming",
        "headphones; in-ear",
    ),
    # Sin precio ni inventario cargados.
    product(
        "MN-HDP-0003",
        "HDP-10002",
        "Nova Sound Lite",
        "NovaTech",
        "BR001",
        "Headphones",
        "Gaming",
        "Auriculares de entrada de gama.",
        1,
        "casual listening",
        "headphones; entry-level",
    ),
]

PRICING = [
    ("MN-MON-0001", "USD", 493.28, 468.62, 5, 1, "2026-10-17"),
    ("MN-MON-0002", "USD", 700.00, 700.00, 0, 1, "2026-10-18"),
    ("MN-HDP-0001", "USD", 150.00, 120.50, 20, 1, "2026-10-19"),
    ("MN-HDP-0002", "USD", 80.00, 80.00, 0, 1, "2026-10-20"),
]

# MN-MON-0001 suma 10 entre los dos depósitos, MN-MON-0002 queda en 0 y
# MN-HDP-0003 no tiene ninguna fila.
INVENTORY = [
    ("MN-MON-0001", "WH-A", 10, 3, 7, "In stock", "2026-10-27 13:00:00"),
    ("MN-MON-0001", "WH-B", 5, 2, 3, "Low stock", "2026-10-27 13:00:00"),
    ("MN-MON-0002", "WH-A", 4, 4, 0, "Out of stock", "2026-10-27 13:00:00"),
    ("MN-MON-0002", "WH-B", 0, 0, 0, "Out of stock", "2026-10-27 13:00:00"),
    ("MN-HDP-0001", "WH-A", 8, 3, 5, "In stock", "2026-10-27 13:00:00"),
    ("MN-HDP-0002", "WH-A", 2, 0, 2, "In stock", "2026-10-27 13:00:00"),
]

# MN-HDP-0003 queda sin relaciones, para probar ese caso.
RELATIONS = [
    ("MN-MON-0001", "MN-MON-0002", "alternative_to", 0.82),
    ("MN-MON-0001", "MN-HDP-0001", "accessory_for", 0.61),
    ("MN-MON-0001", "MN-HDP-0002", "often_bought_with", 0.55),
    ("MN-MON-0002", "MN-MON-0001", "alternative_to", 0.80),
]

SPECIFICATIONS = [
    ("MN-MON-0001", "Display", "Screen Size", None, 24.0, "in"),
    ("MN-MON-0001", "Display", "Panel", "IPS", None, None),
    # "None" es un valor real: el producto no es resistente al agua.
    ("MN-HDP-0001", "Durability", "Water Resistance", "None", None, None),
    ("MN-HDP-0001", "Audio", "Driver", None, 40.0, "mm"),
]


# Inserta el catálogo de prueba en una base con el esquema ya creado.
def populate(connection: sqlite3.Connection) -> None:
    """Carga las filas de prueba en la base.

    Args:
        connection: Conexión abierta, con el esquema creado.
    """
    tables = {
        "brands": BRANDS,
        "categories": CATEGORIES,
        "warehouses": WAREHOUSES,
        "products": PRODUCTS,
        "pricing": PRICING,
        "inventory": INVENTORY,
        "specifications": SPECIFICATIONS,
        "relations": RELATIONS,
    }
    with connection:
        for table, rows in tables.items():
            placeholders = ", ".join("?" * len(rows[0]))
            connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
