"""Tests de backend/cart_tools.py: las dos herramientas del carrito.

Se prueban como las del catálogo: contra la base de prueba, sin modelo y sin
red. Lo que se verifica es lo que la herramienta le devuelve al modelo, porque
es lo único que él puede leer.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend import cart, cart_tools, tool_router, tool_schemas
from backend.carts import CartSession, CartStore


@pytest.fixture
def session() -> CartSession:
    """El carrito de una sesión de prueba, vacío."""
    return CartSession(CartStore(), "s-1")


def test_adding_returns_the_cart_and_a_message_to_repeat(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    result = cart_tools.add_to_cart(catalog_connection, session, "MN-MON-0001", 2)

    assert result["found"] is True
    assert "2 x Nova Vision 24" in result["message"]
    # El total viaja escrito con la moneda: el modelo lo repite, no lo suma.
    assert "USD 937.24" in result["message"]
    assert result["cart"]["total"] == 937.24
    assert result["cart"]["item_count"] == 2


def test_what_the_model_reads_has_no_stock_quantity(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    result = cart_tools.add_to_cart(catalog_connection, session, "MN-MON-0001", 1)

    # La única herramienta que devuelve unidades disponibles es
    # check_availability: si la cantidad saliera de acá, el modelo la repetiría
    # turnos después como si la hubiera consultado de nuevo.
    assert "available_qty" not in result["cart"]["items"][0]


def test_the_line_the_model_reads_has_the_price_of_the_catalog(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    result = cart_tools.add_to_cart(catalog_connection, session, "MN-HDP-0001", 2)

    assert result["cart"]["items"][0] == {
        "product_id": "MN-HDP-0001",
        "name": "Nova Sound Pro",
        "quantity": 2,
        "currency": "USD",
        "unit_price": 120.5,
        "line_total": 241.0,
    }


def test_adding_without_a_quantity_adds_one_unit(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    result = cart_tools.add_to_cart(catalog_connection, session, "MN-MON-0001")

    assert result["cart"]["item_count"] == 1
    assert "1 unidad de 1 producto" in result["message"]


def test_adding_a_product_without_stock_fails_with_the_real_number(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    with pytest.raises(cart.InsufficientStockError):
        cart_tools.add_to_cart(catalog_connection, session, "MN-MON-0002", 1)


def test_removing_takes_the_whole_line(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    cart_tools.add_to_cart(catalog_connection, session, "MN-MON-0001", 3)

    result = cart_tools.remove_from_cart(catalog_connection, session, "MN-MON-0001")

    assert result["cart"]["items"] == []
    assert "El carrito quedó vacío." in result["message"]


def test_removing_something_that_is_not_there_fails(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    with pytest.raises(cart.ProductNotInCartError):
        cart_tools.remove_from_cart(catalog_connection, session, "MN-MON-0001")


def test_the_router_runs_the_cart_tools_with_the_session_cart(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        tool_schemas.ADD_TO_CART,
        {"product_id": "MN-MON-0001", "quantity": "2"},
        ["MN-MON-0001"],
        session,
    )

    assert result["found"] is True
    assert session.store.quantity("s-1", "MN-MON-0001") == 2


def test_the_router_turns_a_cart_error_into_a_result_the_model_can_read(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        tool_schemas.ADD_TO_CART,
        {"product_id": "MN-MON-0002", "quantity": 1},
        ["MN-MON-0002"],
        session,
    )

    # El error vuelve como resultado, no como excepción: la conversación sigue.
    assert result["found"] is False
    assert "no tiene stock disponible" in result["error"]


def test_the_router_rejects_an_invalid_quantity(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        tool_schemas.ADD_TO_CART,
        {"product_id": "MN-MON-0001", "quantity": 0},
        ["MN-MON-0001"],
        session,
    )

    assert result["found"] is False
    assert "mayor a 0" in result["error"]
    assert session.store.items("s-1") == {}


def test_the_cart_tools_only_accept_a_product_seen_in_this_conversation(
    catalog_connection: sqlite3.Connection, session: CartSession
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        tool_schemas.ADD_TO_CART,
        {"product_id": "MN-MON-0001", "quantity": 1},
        [],
        session,
    )

    # Existe en el catálogo, pero no salió de ninguna búsqueda de esta sesión.
    assert result["found"] is False
    assert "no salió de ninguna búsqueda de esta conversación" in result["error"]
    assert session.store.items("s-1") == {}


def test_without_a_cart_the_tool_does_not_run(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        tool_schemas.ADD_TO_CART,
        {"product_id": "MN-MON-0001"},
        ["MN-MON-0001"],
        None,
    )

    assert result["found"] is False
    assert "no tiene un carrito asociado" in result["error"]
