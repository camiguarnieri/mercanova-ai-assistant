"""Escritura del inventario: descontar unidades al confirmar una orden (RF-15).

Es el único módulo que modifica `inventory`. Lo hace depósito por depósito,
porque el stock vive por depósito y no hay una fila con el total.

No abre transacciones ni hace commit: lo llama `orders.py` dentro de la
transacción que también escribe la orden, así no puede quedar stock descontado
sin orden ni orden sin stock descontado.
"""

from __future__ import annotations

import sqlite3

__all__ = ["OUT_OF_STOCK", "StockWriteError", "warehouse_stock", "reduce_stock"]

# El estado que queda cuando un depósito se queda sin unidades disponibles. Es
# el mismo texto que usa el dataset de la cátedra para ese caso.
OUT_OF_STOCK = "Out of stock"

# De dónde se descuenta primero: del depósito que más tiene, así un pedido
# grande se cubre con la menor cantidad de depósitos posible.
STOCK_BY_WAREHOUSE = """
SELECT warehouse_id, available_qty
FROM inventory
WHERE product_id = ? AND available_qty > 0
ORDER BY available_qty DESC, warehouse_id
"""

# El stock reservado no se toca: salen unidades del depósito, así que bajan
# on_hand_qty y available_qty juntas y el CHECK de la tabla se sigue cumpliendo.
REDUCE_IN_WAREHOUSE = """
UPDATE inventory
SET on_hand_qty = on_hand_qty - ?,
    available_qty = available_qty - ?,
    inventory_status = CASE WHEN available_qty - ? = 0 THEN ? ELSE inventory_status END
WHERE product_id = ? AND warehouse_id = ?
"""


class StockWriteError(RuntimeError):
    """No se pudo descontar el stock pedido."""


# Suma las unidades disponibles de un producto en todos los depósitos.
def warehouse_stock(connection: sqlite3.Connection, product_id: str) -> int:
    """Devuelve el stock disponible de un producto.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto.

    Returns:
        La suma de `available_qty` de los depósitos. 0 si el producto no tiene
        inventario cargado.
    """
    row = connection.execute(
        "SELECT COALESCE(SUM(available_qty), 0) AS total FROM inventory WHERE product_id = ?",
        [product_id],
    ).fetchone()
    return int(row["total"])


# Descuenta unidades de un producto, repartiéndolas entre los depósitos.
def reduce_stock(connection: sqlite3.Connection, product_id: str, quantity: int) -> None:
    """Baja el stock disponible de un producto (RF-15).

    Args:
        connection: Conexión abierta con `db.connect()`, dentro de la
            transacción de la orden.
        product_id: Identificador del producto comprado.
        quantity: Unidades a descontar, mayor a 0.

    Raises:
        StockWriteError: Si entre todos los depósitos no hay tantas unidades.
            Quien llama tiene que dejar caer la transacción: el stock no puede
            quedar descontado a medias.
    """
    remaining = quantity
    for row in connection.execute(STOCK_BY_WAREHOUSE, [product_id]).fetchall():
        if remaining == 0:
            break
        taken = min(remaining, int(row["available_qty"]))
        connection.execute(
            REDUCE_IN_WAREHOUSE,
            [taken, taken, taken, OUT_OF_STOCK, product_id, row["warehouse_id"]],
        )
        remaining -= taken

    if remaining:
        raise StockWriteError(
            f"No se pudo descontar el stock de '{product_id}': faltaron {remaining} "
            f"unidades de las {quantity} pedidas. La compra no se registró."
        )
