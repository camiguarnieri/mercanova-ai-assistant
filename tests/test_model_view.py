"""Tests de backend/model_view.py: qué parte del resultado ve el modelo.

Las herramientas devuelven el dato completo, que usa la interfaz, y al modelo le
llega una copia sin los campos que se le cruzaban de un producto a otro.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend import model_view, product_lookup, tools

# Las cuatro herramientas y el lookup, con una invocación válida cada uno.
EVERY_SOURCE = [
    ("search_products", {"category": "Headphones"}),
    ("get_product_details", {"product_id": "MN-MON-0001"}),
    ("compare_products", {"product_ids": ["MN-MON-0001", "MN-MON-0002"]}),
    ("get_related_products", {"product_id": "MN-MON-0001"}),
]


# Busca una clave en cualquier parte de un resultado, por anidado que esté.
def contains_key(value: object, key: str) -> bool:
    """Dice si la clave aparece en el resultado, a cualquier profundidad."""
    if isinstance(value, dict):
        return key in value or any(contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, key) for item in value)
    return False


def test_the_hidden_field_is_taken_out() -> None:
    result = {"product_id": "MN-MON-0001", "not_recommended_for": "gaming"}

    assert model_view.for_the_model(result) == {"product_id": "MN-MON-0001"}


def test_the_hidden_field_is_taken_out_at_any_depth() -> None:
    result = {"related": [{"product": {"name": "X", "not_recommended_for": "gaming"}}]}

    assert model_view.for_the_model(result) == {"related": [{"product": {"name": "X"}}]}


def test_the_rest_of_the_result_travels_untouched() -> None:
    result = {"found": True, "products": [{"name": "X", "current_price": 10.5}]}

    assert model_view.for_the_model(result) == result


def test_the_result_that_was_received_is_not_modified() -> None:
    # La interfaz lo usa entero después: si se tocara acá, la tarjeta perdería
    # el dato.
    result = {"products": [{"not_recommended_for": "gaming"}]}

    model_view.for_the_model(result)

    assert result == {"products": [{"not_recommended_for": "gaming"}]}


@pytest.mark.parametrize(
    ("name", "arguments"), EVERY_SOURCE, ids=[source[0] for source in EVERY_SOURCE]
)
def test_no_tool_sends_the_hidden_field_to_the_model(
    catalog_connection: sqlite3.Connection, name: str, arguments: dict[str, object]
) -> None:
    # Con el campo en null y con la frase "el catálogo no lo aclara", las dos
    # veces el modelo le puso a un producto el valor de otro. Deja de viajar.
    result = getattr(tools, name)(catalog_connection, **arguments)

    assert not contains_key(model_view.for_the_model(result), "not_recommended_for")


def test_the_lookup_does_not_send_the_hidden_field_either(
    catalog_connection: sqlite3.Connection,
) -> None:
    lookup = product_lookup.lookup_message(catalog_connection, "¿tenés el Nova Vision 24?")

    assert not contains_key(model_view.for_the_model(lookup), "not_recommended_for")


# Las que sí traen el campo. `get_related_products` queda afuera: devuelve
# `Product`, que nunca tuvo not_recommended_for, y la interfaz no lo muestra
# para un relacionado.
WITH_THE_FIELD = [source for source in EVERY_SOURCE if source[0] != "get_related_products"]


@pytest.mark.parametrize(
    ("name", "arguments"), WITH_THE_FIELD, ids=[source[0] for source in WITH_THE_FIELD]
)
def test_the_tools_still_return_the_field_for_the_interface(
    catalog_connection: sqlite3.Connection, name: str, arguments: dict[str, object]
) -> None:
    # El usuario no pierde el dato: la tarjeta lo imprime desde el resultado
    # completo. Si una herramienta dejara de traerlo, lo perdería.
    result = getattr(tools, name)(catalog_connection, **arguments)

    assert contains_key(result, "not_recommended_for")


def test_the_lookup_still_returns_the_field_for_the_interface(
    catalog_connection: sqlite3.Connection,
) -> None:
    lookup = product_lookup.lookup_message(catalog_connection, "¿tenés el Nova Vision 24?")

    assert contains_key(lookup, "not_recommended_for")
