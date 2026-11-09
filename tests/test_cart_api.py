"""Tests de backend/cart_api.py: los endpoints del carrito y del checkout.

Con el cliente de test de FastAPI, contra la base de prueba y con un almacén de
carritos propio de cada test. Ningún test llama al modelo ni sale a la red.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import api, db
from backend.carts import CartStore
from backend.dependencies import get_cart_store

# El arranque real, guardado antes de que la fixture de conftest lo reemplace
# por nada: el test de abajo lo corre a propósito, contra la base de prueba.
ENSURE_SCHEMA = api.ensure_schema

CHECKOUT = {
    "session_id": "s-1",
    "customer_name": "Camila Guarnieri",
    "shipping_address": "Av. Siempreviva 742, Montevideo",
    "confirmed": True,
}


@pytest.fixture
def cart_store() -> CartStore:
    """El almacén de carritos que usa el cliente de test."""
    return CartStore()


@pytest.fixture
def client(catalog_database: Path, cart_store: CartStore) -> Iterator[TestClient]:
    """Un cliente apuntado a la base de prueba y a un carrito vacío."""
    api.app.dependency_overrides[api.get_connection_scope] = lambda: partial(
        db.connection_scope, catalog_database
    )
    api.app.dependency_overrides[get_cart_store] = lambda: cart_store
    with TestClient(api.app) as test_client:
        yield test_client
    api.app.dependency_overrides.clear()


# Agrega un producto al carrito de la sesión de prueba.
def add(client: TestClient, product_id: str, quantity: int = 1) -> Any:
    """Llama al endpoint de agregar y devuelve la respuesta."""
    return client.post(
        "/cart/items",
        json={"session_id": "s-1", "product_id": product_id, "quantity": quantity},
    )


def test_a_new_session_has_an_empty_cart(client: TestClient) -> None:
    response = client.get("/cart", params={"session_id": "s-1"})

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "s-1",
        "items": [],
        "currency": None,
        "total": 0.0,
        "item_count": 0,
    }


def test_adding_a_product_answers_with_the_cart(client: TestClient) -> None:
    response = add(client, "MN-MON-0001", 2)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 937.24
    assert body["item_count"] == 2
    assert set(body["items"][0]) == {
        "product_id",
        "name",
        "brand",
        "quantity",
        "currency",
        "unit_price",
        "line_total",
        "available_qty",
    }


def test_the_cart_survives_between_requests_of_the_same_session(
    client: TestClient,
) -> None:
    add(client, "MN-MON-0001", 1)
    add(client, "MN-HDP-0001", 2)

    body = client.get("/cart", params={"session_id": "s-1"}).json()

    assert [line["product_id"] for line in body["items"]] == ["MN-MON-0001", "MN-HDP-0001"]


def test_the_cart_of_another_session_is_empty(client: TestClient) -> None:
    add(client, "MN-MON-0001", 1)

    body = client.get("/cart", params={"session_id": "s-2"}).json()

    assert body["items"] == []


def test_a_product_that_does_not_exist_is_a_404(client: TestClient) -> None:
    response = add(client, "MN-NOPE-0001", 1)

    assert response.status_code == 404
    assert "No existe el producto" in response.json()["detail"]


def test_a_product_without_stock_is_a_409(client: TestClient) -> None:
    response = add(client, "MN-MON-0002", 1)

    assert response.status_code == 409
    assert "no tiene stock disponible" in response.json()["detail"]


def test_more_units_than_available_is_a_409(client: TestClient) -> None:
    response = add(client, "MN-HDP-0001", 6)

    assert response.status_code == 409
    assert "hay 5 unidades disponibles" in response.json()["detail"]


@pytest.mark.parametrize("quantity", [0, -3])
def test_a_quantity_that_is_not_positive_is_a_422(client: TestClient, quantity: int) -> None:
    response = add(client, "MN-MON-0001", quantity)

    assert response.status_code == 422


def test_a_quantity_that_is_not_a_number_is_a_422(client: TestClient) -> None:
    response = client.post(
        "/cart/items",
        json={"session_id": "s-1", "product_id": "MN-MON-0001", "quantity": "dos"},
    )

    assert response.status_code == 422


def test_the_quantity_of_a_line_can_be_changed(client: TestClient) -> None:
    add(client, "MN-MON-0001", 1)

    response = client.put(
        "/cart/items/MN-MON-0001", json={"session_id": "s-1", "quantity": 3}
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == 3


def test_changing_a_line_that_is_not_in_the_cart_is_a_404(client: TestClient) -> None:
    response = client.put(
        "/cart/items/MN-MON-0001", json={"session_id": "s-1", "quantity": 3}
    )

    assert response.status_code == 404


def test_a_product_can_be_removed(client: TestClient) -> None:
    add(client, "MN-MON-0001", 1)

    response = client.delete("/cart/items/MN-MON-0001", params={"session_id": "s-1"})

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_removing_something_that_is_not_in_the_cart_is_a_404(client: TestClient) -> None:
    response = client.delete("/cart/items/MN-MON-0001", params={"session_id": "s-1"})

    assert response.status_code == 404


def test_the_checkout_creates_an_order(client: TestClient) -> None:
    add(client, "MN-MON-0001", 2)

    response = client.post("/checkout", json=CHECKOUT)

    assert response.status_code == 201
    body = response.json()
    assert body["order_id"].startswith("MN-ORD-")
    assert body["customer_name"] == "Camila Guarnieri"
    assert body["shipping_address"] == "Av. Siempreviva 742, Montevideo"
    assert body["total_amount"] == 937.24
    assert body["items"][0]["unit_price"] == 468.62
    assert body["created_at"]


def test_the_checkout_empties_the_cart_and_discounts_the_stock(
    client: TestClient,
) -> None:
    add(client, "MN-MON-0001", 4)

    client.post("/checkout", json=CHECKOUT)

    assert client.get("/cart", params={"session_id": "s-1"}).json()["items"] == []
    product = client.get("/products/MN-MON-0001").json()
    assert product["available_qty"] == 6


def test_the_checkout_without_the_explicit_confirmation_is_a_422(
    client: TestClient,
) -> None:
    add(client, "MN-MON-0001", 1)

    response = client.post("/checkout", json={**CHECKOUT, "confirmed": False})

    assert response.status_code == 422
    # No se creó nada: el carrito sigue como estaba (RF-12).
    assert client.get("/cart", params={"session_id": "s-1"}).json()["item_count"] == 1
    assert client.get("/orders", params={"session_id": "s-1"}).json() == []


def test_the_checkout_without_the_confirmation_field_is_a_422(client: TestClient) -> None:
    add(client, "MN-MON-0001", 1)
    payload = {key: value for key, value in CHECKOUT.items() if key != "confirmed"}

    assert client.post("/checkout", json=payload).status_code == 422


@pytest.mark.parametrize("field", ["customer_name", "shipping_address"])
def test_the_checkout_needs_the_shipping_details(client: TestClient, field: str) -> None:
    add(client, "MN-MON-0001", 1)

    response = client.post("/checkout", json={**CHECKOUT, field: "   "})

    # RF-13: nombre y dirección son obligatorios, y no alcanzan los espacios.
    assert response.status_code == 422


def test_the_checkout_of_an_empty_cart_is_a_409(client: TestClient) -> None:
    response = client.post("/checkout", json=CHECKOUT)

    assert response.status_code == 409
    assert "carrito está vacío" in response.json()["detail"]


def test_the_checkout_does_not_take_payment_details(client: TestClient) -> None:
    add(client, "MN-MON-0001", 1)

    response = client.post("/checkout", json={**CHECKOUT, "card_number": "4111111111111111"})

    # No hay pasarela de pago: un campo de tarjeta no es parte del contrato.
    assert response.status_code == 422


def test_the_history_lists_the_orders_of_the_session(client: TestClient) -> None:
    add(client, "MN-MON-0001", 1)
    first = client.post("/checkout", json=CHECKOUT).json()
    add(client, "MN-HDP-0001", 1)
    second = client.post("/checkout", json=CHECKOUT).json()

    body = client.get("/orders", params={"session_id": "s-1"}).json()

    assert [order["order_id"] for order in body] == [second["order_id"], first["order_id"]]


def test_the_history_of_a_session_without_orders_is_empty(client: TestClient) -> None:
    assert client.get("/orders", params={"session_id": "s-9"}).json() == []


def test_an_order_can_be_read_by_its_identifier(client: TestClient) -> None:
    add(client, "MN-MON-0001", 1)
    order_id = client.post("/checkout", json=CHECKOUT).json()["order_id"]

    response = client.get(f"/orders/{order_id}")

    assert response.status_code == 200
    assert response.json()["order_id"] == order_id


def test_an_order_that_does_not_exist_is_a_404(client: TestClient) -> None:
    response = client.get("/orders/MN-ORD-20261109-AAAAAAAA")

    assert response.status_code == 404


def test_a_cart_with_two_currencies_is_a_409(
    client: TestClient, catalog_database: Path
) -> None:
    add(client, "MN-MON-0001", 1)
    add(client, "MN-HDP-0001", 1)
    with db.connection_scope(catalog_database) as connection:
        with connection:
            connection.execute(
                "UPDATE pricing SET currency = 'UYU' WHERE product_id = 'MN-HDP-0001'"
            )

    response = client.post("/checkout", json=CHECKOUT)

    assert response.status_code == 409
    assert "monedas distintas" in response.json()["detail"]


def test_the_startup_creates_the_order_tables_without_touching_the_catalog(
    catalog_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Una base cargada antes de que existieran orders y order_items: el
    # arranque las crea y deja el catálogo como estaba.
    with db.connection_scope(catalog_database) as connection:
        with connection:
            connection.execute("DROP TABLE order_items")
            connection.execute("DROP TABLE orders")
        before = db.table_counts(connection)
    monkeypatch.setenv("DATABASE_PATH", str(catalog_database))

    ENSURE_SCHEMA()

    with db.connection_scope(catalog_database) as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"orders", "order_items"} <= tables
        assert db.table_counts(connection) == before
