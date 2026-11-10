"""Tests de backend/inventory.py: el descuento de stock (RF-15)."""

from __future__ import annotations

import sqlite3

import pytest

from backend import inventory


# Devuelve el inventario de un producto, depósito por depósito.
def rows_of(connection: sqlite3.Connection, product_id: str) -> list[tuple[str, int, int, int]]:
    """Lee las filas de inventory de un producto, para verificar el descuento."""
    return [
        (row["warehouse_id"], row["on_hand_qty"], row["reserved_qty"], row["available_qty"])
        for row in connection.execute(
            "SELECT warehouse_id, on_hand_qty, reserved_qty, available_qty FROM inventory "
            "WHERE product_id = ? ORDER BY warehouse_id",
            [product_id],
        ).fetchall()
    ]


def test_the_stock_of_a_product_sums_the_warehouses(
    catalog_connection: sqlite3.Connection,
) -> None:
    # MN-MON-0001 tiene 7 en WH-A y 3 en WH-B.
    assert inventory.warehouse_stock(catalog_connection, "MN-MON-0001") == 10


def test_a_product_without_inventory_has_no_stock(
    catalog_connection: sqlite3.Connection,
) -> None:
    assert inventory.warehouse_stock(catalog_connection, "MN-HDP-0003") == 0


def test_reducing_takes_the_units_from_the_fullest_warehouse(
    catalog_connection: sqlite3.Connection,
) -> None:
    inventory.reduce_stock(catalog_connection, "MN-MON-0001", 4)

    # WH-A tenía 7 disponibles y WH-B 3: salen los 4 de WH-A.
    assert rows_of(catalog_connection, "MN-MON-0001") == [
        ("WH-A", 6, 3, 3),
        ("WH-B", 5, 2, 3),
    ]


def test_reducing_spreads_across_warehouses_when_one_is_not_enough(
    catalog_connection: sqlite3.Connection,
) -> None:
    inventory.reduce_stock(catalog_connection, "MN-MON-0001", 9)

    # Se vacía WH-A y lo que falta sale de WH-B.
    assert rows_of(catalog_connection, "MN-MON-0001") == [
        ("WH-A", 3, 3, 0),
        ("WH-B", 3, 2, 1),
    ]
    assert inventory.warehouse_stock(catalog_connection, "MN-MON-0001") == 1


def test_the_reserved_stock_is_not_touched(
    catalog_connection: sqlite3.Connection,
) -> None:
    inventory.reduce_stock(catalog_connection, "MN-MON-0001", 7)

    # El CHECK de la tabla exige available = on_hand - reserved, y se cumple.
    for _, on_hand, reserved, available in rows_of(catalog_connection, "MN-MON-0001"):
        assert available == on_hand - reserved


def test_a_warehouse_that_runs_out_is_marked_as_out_of_stock(
    catalog_connection: sqlite3.Connection,
) -> None:
    inventory.reduce_stock(catalog_connection, "MN-MON-0001", 7)

    status = catalog_connection.execute(
        "SELECT inventory_status FROM inventory "
        "WHERE product_id = 'MN-MON-0001' AND warehouse_id = 'WH-A'"
    ).fetchone()["inventory_status"]
    assert status == inventory.OUT_OF_STOCK


def test_asking_for_more_units_than_there_are_fails(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(inventory.StockWriteError) as error:
        inventory.reduce_stock(catalog_connection, "MN-MON-0001", 11)

    assert "faltaron 1 unidades" in str(error.value)


def test_reducing_a_product_without_inventory_fails(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(inventory.StockWriteError):
        inventory.reduce_stock(catalog_connection, "MN-HDP-0003", 1)
