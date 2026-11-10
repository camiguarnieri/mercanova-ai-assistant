"""El SQL de las órdenes: insertar una y leer el historial de una sesión.

Solo arma texto SQL. No abre conexiones ni decide nada: eso es de `orders.py`.
"""

from __future__ import annotations

__all__ = [
    "INSERT_ORDER",
    "INSERT_ORDER_ITEM",
    "ORDERS_BY_SESSION",
    "ORDER_BY_ID",
    "ITEMS_OF_ORDERS",
]

INSERT_ORDER = """
INSERT INTO orders (
    order_id, session_id, created_at, customer_name, shipping_address, currency, total_amount
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""

INSERT_ORDER_ITEM = """
INSERT INTO order_items (
    order_id, product_id, name, quantity, unit_price, currency, line_total
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""

ORDER_COLUMNS = """
    order_id, session_id, created_at, customer_name, shipping_address,
    currency, total_amount
"""

# La más nueva primero: es el orden en el que se muestra el historial (RF-16).
ORDERS_BY_SESSION = f"""
SELECT {ORDER_COLUMNS}
FROM orders
WHERE session_id = ?
ORDER BY created_at DESC, order_id DESC
"""

ORDER_BY_ID = f"""
SELECT {ORDER_COLUMNS}
FROM orders
WHERE order_id = ?
"""

# Las líneas de varias órdenes en una sola consulta: el historial trae todas las
# órdenes de la sesión y sin esto haría una consulta por orden. El IN se arma
# con un placeholder por order_id.
ITEMS_OF_ORDERS = """
SELECT order_id, product_id, name, quantity, unit_price, currency, line_total
FROM order_items
WHERE order_id IN ({placeholders})
ORDER BY rowid
"""
