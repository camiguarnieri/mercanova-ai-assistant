"""Tests de backend/cart.py: las reglas del carrito sobre la base de prueba.

El stock sale siempre del catálogo de prueba, no de números escritos acá:
MN-MON-0001 tiene 10 unidades entre dos depósitos, MN-MON-0002 tiene 0,
MN-HDP-0001 tiene 5, MN-HDP-0002 está dado de baja y MN-HDP-0003 no tiene
precio cargado. Ningún test llama al modelo ni sale a la red.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend import cart, catalog
from backend.carts import CartStore


@pytest.fixture
def store() -> CartStore:
    """Un almacén de carritos vacío, propio de cada test."""
    return CartStore()


def test_a_session_without_a_cart_gets_an_empty_one(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    basket = cart.view(catalog_connection, store, "s-1")

    assert basket.items == []
    assert basket.total == 0.0
    assert basket.item_count == 0
    assert basket.currency is None


def test_adding_a_product_puts_it_in_the_cart_with_the_catalog_price(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    basket = cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 2)

    line = basket.items[0]
    assert line.product_id == "MN-MON-0001"
    assert line.name == "Nova Vision 24"
    assert line.quantity == 2
    # El precio no se guarda en el carrito: sale de pricing en este momento.
    assert line.unit_price == 468.62
    assert line.line_total == 937.24
    assert basket.total == 937.24
    assert basket.currency == "USD"
    assert basket.item_count == 2


def test_adding_the_same_product_twice_sums_the_quantities(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 2)
    basket = cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 3)

    assert [line.quantity for line in basket.items] == [5]


def test_the_default_quantity_is_one(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    basket = cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001")

    assert basket.items[0].quantity == 1


def test_the_total_sums_the_lines(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)
    basket = cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 2)

    assert basket.total == round(468.62 + 120.50 * 2, 2)
    assert basket.item_count == 3


def test_a_product_that_does_not_exist_cannot_be_added(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    with pytest.raises(catalog.ProductNotFoundError):
        cart.add_item(catalog_connection, store, "s-1", "MN-NOPE-0001", 1)

    assert store.items("s-1") == {}


def test_a_product_without_stock_cannot_be_added(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    # MN-MON-0002 tiene available_qty 0 en los dos depósitos (RF-10).
    with pytest.raises(cart.InsufficientStockError) as error:
        cart.add_item(catalog_connection, store, "s-1", "MN-MON-0002", 1)

    assert "no tiene stock disponible" in str(error.value)
    assert store.items("s-1") == {}


def test_more_units_than_available_cannot_be_added(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    with pytest.raises(cart.InsufficientStockError) as error:
        cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 6)

    # El mensaje dice el número real de la base, no uno escrito a mano.
    assert "hay 5 unidades disponibles" in str(error.value)
    assert "hasta 5" in str(error.value)


def test_the_stock_is_checked_against_the_whole_line_not_the_added_amount(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 3)

    with pytest.raises(cart.InsufficientStockError):
        cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 3)

    # La línea queda como estaba: el segundo intento no agregó nada.
    assert store.quantity("s-1", "MN-HDP-0001") == 3


def test_a_discontinued_product_cannot_be_added(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    with pytest.raises(cart.ProductUnavailableError) as error:
        cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0002", 1)

    assert "dado de baja" in str(error.value)


def test_a_product_without_a_price_cannot_be_added(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    with pytest.raises(cart.ProductUnavailableError) as error:
        cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0003", 1)

    assert "no tiene precio cargado" in str(error.value)


@pytest.mark.parametrize("quantity", [0, -1, -10])
def test_a_quantity_that_is_not_positive_is_rejected(
    catalog_connection: sqlite3.Connection, store: CartStore, quantity: int
) -> None:
    with pytest.raises(cart.InvalidQuantityError):
        cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", quantity)

    assert store.items("s-1") == {}


@pytest.mark.parametrize("quantity", ["dos", "", None, "2,5", [2], True, "nan", "inf"])
def test_a_quantity_that_is_not_a_number_is_rejected(
    catalog_connection: sqlite3.Connection, store: CartStore, quantity: object
) -> None:
    with pytest.raises(cart.InvalidQuantityError):
        cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", quantity)


def test_a_quantity_with_decimals_is_rejected(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    with pytest.raises(cart.InvalidQuantityError) as error:
        cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1.5)

    assert "sin decimales" in str(error.value)


def test_a_quantity_written_as_text_is_accepted(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    # El modelo manda los números como texto más de una vez.
    basket = cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", "3")

    assert basket.items[0].quantity == 3


def test_the_quantity_of_a_line_can_be_changed(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 2)

    basket = cart.set_quantity(catalog_connection, store, "s-1", "MN-MON-0001", 4)

    assert basket.items[0].quantity == 4


def test_changing_the_quantity_also_checks_the_stock(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 1)

    with pytest.raises(cart.InsufficientStockError):
        cart.set_quantity(catalog_connection, store, "s-1", "MN-HDP-0001", 9)

    assert store.quantity("s-1", "MN-HDP-0001") == 1


def test_the_quantity_of_a_product_that_is_not_in_the_cart_cannot_be_changed(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    with pytest.raises(cart.ProductNotInCartError):
        cart.set_quantity(catalog_connection, store, "s-1", "MN-MON-0001", 2)


def test_a_product_can_be_removed(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 2)
    cart.add_item(catalog_connection, store, "s-1", "MN-HDP-0001", 1)

    basket = cart.remove_item(catalog_connection, store, "s-1", "MN-MON-0001")

    assert [line.product_id for line in basket.items] == ["MN-HDP-0001"]


def test_removing_something_that_is_not_in_the_cart_fails(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    with pytest.raises(cart.ProductNotInCartError):
        cart.remove_item(catalog_connection, store, "s-1", "MN-MON-0001")


def test_each_session_has_its_own_cart(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)

    assert cart.view(catalog_connection, store, "s-2").items == []


def test_the_line_shows_the_stock_available_right_now(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)

    # El stock de la línea se lee de la base, no se guarda al agregar.
    catalog_connection.execute(
        "UPDATE inventory SET on_hand_qty = 1, available_qty = 1, reserved_qty = 0 "
        "WHERE product_id = 'MN-MON-0001'"
    )

    assert cart.view(catalog_connection, store, "s-1").items[0].available_qty == 2


def test_a_product_that_left_the_catalog_disappears_from_the_cart(
    catalog_connection: sqlite3.Connection, store: CartStore
) -> None:
    cart.add_item(catalog_connection, store, "s-1", "MN-MON-0001", 1)
    catalog_connection.execute("DELETE FROM relations")
    catalog_connection.execute("DELETE FROM inventory WHERE product_id = 'MN-MON-0001'")
    catalog_connection.execute("DELETE FROM pricing WHERE product_id = 'MN-MON-0001'")
    catalog_connection.execute("DELETE FROM specifications WHERE product_id = 'MN-MON-0001'")
    catalog_connection.execute("DELETE FROM products WHERE product_id = 'MN-MON-0001'")

    # No se puede mostrar su precio, y dejarlo trabaría el carrito entero.
    assert cart.view(catalog_connection, store, "s-1").items == []
