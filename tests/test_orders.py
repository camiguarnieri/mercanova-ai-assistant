"""Tests de backend/orders.py: confirmación de la compra e historial.

Verifican lo que tiene que quedar consistente después de confirmar: la orden
con sus precios congelados, el stock descontado en la base y el carrito vacío.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from backend import cart, inventory, orders
from backend.carts import CartStore


@pytest.fixture
def store() -> CartStore:
    """Un almacén de carritos vacío, propio de cada test."""
    return CartStore()


# Confirma una compra con datos de envío de prueba.
def confirm(connection: sqlite3.Connection, store: CartStore, session_id: str = "s-1"):
    """Llama al checkout con un nombre y una dirección cualquiera."""
    return orders.checkout(
        connection,
        store,
        session_id,
        customer_name="  Camila Guarnieri  ",
        shipping_address="  Av. Siempreviva 742, Montevideo  ",
    )


def test_the_order_id_has_the_project_prefix_and_the_date() -> None:
    order_id = orders.new_order_id(datetime(2026, 11, 9, tzinfo=timezone.utc))

    assert order_id.startswith("MN-ORD-20261109-")
    assert len(order_id) == len("MN-ORD-20261109-") + 8


def test_two_orders_of_the_same_day_do_not_collide() -> None:
    moment = datetime(2026, 11, 9, tzinfo=timezone.utc)

    assert orders.new_order_id(moment) != orders.new_order_id(moment)


def test_confirming_creates_an_order_with_its_lines(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 2)
    cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 1)

    order = confirm(catalog_connection, store)

    assert order.order_id.startswith("MN-ORD-")
    assert order.session_id == "s-1"
    assert order.customer_name == "Camila Guarnieri"
    assert order.shipping_address == "Av. Siempreviva 742, Montevideo"
    assert [(line.product_id, line.quantity) for line in order.items] == [
        ("MN-MON-0001", 2),
        ("MN-HDP-0001", 1),
    ]
    assert order.total_amount == round(468.62 * 2 + 120.50, 2)
    assert order.currency == "USD"


def test_the_order_keeps_the_price_of_the_moment_of_the_purchase(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)
    order = confirm(catalog_connection, store)

    catalog_connection.execute(
        "UPDATE pricing SET current_price = 1.0 WHERE product_id = 'MN-MON-0001'"
    )

    # La orden guardada sigue diciendo lo que el usuario confirmó (RF-14).
    stored = orders.get_order(catalog_connection, order.order_id)
    assert stored.items[0].unit_price == 468.62
    assert stored.items[0].name == "Nova Vision 24"
    assert stored.total_amount == 468.62


def test_confirming_discounts_the_stock_in_the_database(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 4)

    confirm(catalog_connection, store)

    # RF-15: el estado queda coherente, el stock baja en la base.
    assert inventory.warehouse_stock(catalog_connection, "MN-MON-0001") == 6


def test_confirming_empties_the_cart(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)

    confirm(catalog_connection, store)

    assert store.items("s-1") == {}


def test_an_empty_cart_cannot_be_confirmed(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    with pytest.raises(cart.EmptyCartError) as error:
        confirm(catalog_connection, store)

    assert "carrito está vacío" in str(error.value)
    assert orders.list_orders(catalog_connection, "s-1") == []


def test_the_stock_is_checked_again_when_confirming(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 8)
    # Entre agregar y confirmar, el stock bajó.
    catalog_connection.execute(
        "UPDATE inventory SET on_hand_qty = 1, reserved_qty = 0, available_qty = 1 "
        "WHERE product_id = 'MN-MON-0001'"
    )

    with pytest.raises(cart.InsufficientStockError):
        confirm(catalog_connection, store)

    # No se creó la orden ni se tocó el stock, y el carrito sigue entero.
    assert orders.list_orders(catalog_connection, "s-1") == []
    assert inventory.warehouse_stock(catalog_connection, "MN-MON-0001") == 2
    assert store.quantity("s-1", "MN-MON-0001") == 8


def test_the_order_and_the_stock_are_written_in_the_same_transaction(
    catalog_connection: sqlite3.Connection,
    store: CartStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 2)
    cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 1)
    before = inventory.warehouse_stock(catalog_connection, "MN-MON-0001")

    # Falla el descuento de la segunda línea, con la primera ya descontada y la
    # orden ya escrita: todo eso se tiene que deshacer.
    real_reduce = inventory.reduce_stock

    def failing_reduce(connection: sqlite3.Connection, product_id: str, quantity: int) -> None:
        if product_id == "MN-HDP-0001":
            raise inventory.StockWriteError("falla simulada al descontar el stock")
        real_reduce(connection, product_id, quantity)

    monkeypatch.setattr(orders.inventory, "reduce_stock", failing_reduce)

    with pytest.raises(inventory.StockWriteError):
        confirm(catalog_connection, store)

    assert orders.list_orders(catalog_connection, "s-1") == []
    assert inventory.warehouse_stock(catalog_connection, "MN-MON-0001") == before
    assert store.quantity("s-1", "MN-MON-0001") == 2


def test_a_cart_with_two_currencies_cannot_be_confirmed(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)
    cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 1)
    catalog_connection.execute(
        "UPDATE pricing SET currency = 'UYU' WHERE product_id = 'MN-HDP-0001'"
    )

    with pytest.raises(orders.OrderError) as error:
        confirm(catalog_connection, store)

    assert "monedas distintas" in str(error.value)


def test_the_history_brings_the_orders_of_the_session_newest_first(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)
    first = confirm(catalog_connection, store)
    cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 2)
    second = confirm(catalog_connection, store)

    history = orders.list_orders(catalog_connection, "s-1")

    assert [order.order_id for order in history] == [second.order_id, first.order_id]
    assert [line.quantity for line in history[0].items] == [2]


def test_the_history_of_another_session_is_empty(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)
    confirm(catalog_connection, store)

    assert orders.list_orders(catalog_connection, "s-2") == []


def test_an_order_that_does_not_exist_is_an_error(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(orders.OrderNotFoundError):
        orders.get_order(catalog_connection, "MN-ORD-20261109-AAAAAAAA")
