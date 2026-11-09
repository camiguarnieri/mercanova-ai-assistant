"""Tests de backend/product_lookup.py: el paso determinístico de nombres.

Los dos modelos que probamos no buscan un producto que el usuario nombra, así
que el catálogo se consulta antes del turno del modelo. Acá se verifica qué
detecta la heurística y qué no.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend import product_lookup


def test_a_product_named_in_the_message_is_found(
    catalog_connection: sqlite3.Connection,
) -> None:
    found = product_lookup.find_products(catalog_connection, "¿tenés el Nova Vision 24?")

    assert [product.name for product in found] == ["Nova Vision 24"]


@pytest.mark.parametrize(
    "message",
    [
        "¿tenés el Nova Vision 24?",
        "nova vision 24",
        "NOVA VISION 24",
        "me interesa el   Nova Vision 24   que vi",
    ],
)
def test_the_name_is_found_however_it_was_written(
    catalog_connection: sqlite3.Connection, message: str
) -> None:
    # Sin distinguir mayúsculas y con los espacios normalizados.
    found = product_lookup.find_products(catalog_connection, message)

    assert [product.name for product in found] == ["Nova Vision 24"]


def test_a_product_without_stock_is_found_the_same(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Como el Aether Dock Hub 7 del catálogo real: existe y no tiene stock.
    found = product_lookup.find_products(catalog_connection, "quiero el Flux Vision 27")

    assert found[0].in_stock is False
    assert found[0].current_price == 700.0


def test_the_result_brings_what_the_model_needs_to_answer(
    catalog_connection: sqlite3.Connection,
) -> None:
    found = product_lookup.find_products(catalog_connection, "el Nova Vision 24")

    assert found[0].product_id == "MN-MON-0001"
    assert found[0].recommended_for == "office work; programming"
    assert found[0].not_recommended_for == "gaming"


def test_a_product_that_is_not_in_the_catalog_is_not_found(
    catalog_connection: sqlite3.Connection,
) -> None:
    assert product_lookup.find_products(catalog_connection, "¿tenés el iPhone 15 Pro?") == []


def test_a_discontinued_product_is_not_found(
    catalog_connection: sqlite3.Connection,
) -> None:
    # No se puede ofrecer algo que no se vende más.
    assert product_lookup.find_products(catalog_connection, "quiero los Flux Buds") == []


def test_a_message_without_a_name_finds_nothing(
    catalog_connection: sqlite3.Connection,
) -> None:
    assert product_lookup.find_products(catalog_connection, "quiero auriculares") == []


def test_an_empty_message_finds_nothing(catalog_connection: sqlite3.Connection) -> None:
    assert product_lookup.find_products(catalog_connection, "   ") == []


def test_the_longest_name_comes_first(catalog_connection: sqlite3.Connection) -> None:
    # "Nova Sound Pro" y "Nova Sound Lite" empiezan igual: el nombre más largo
    # es el más específico.
    found = product_lookup.find_products(
        catalog_connection, "comparame el Nova Sound Pro con el Nova Sound Lite"
    )

    assert [product.name for product in found] == ["Nova Sound Lite", "Nova Sound Pro"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("¿tenés el iPhone 15 Pro?", "iPhone 15 Pro"),
        ("busco un Aether Dock Hub 7", "Aether Dock Hub 7"),
        ("Aether Dock Hub 7, ¿lo tenés?", "Aether Dock Hub 7"),
        ("quiero el Magic Keyboard", "Magic Keyboard"),
    ],
)
def test_a_name_that_the_user_wrote_is_detected(message: str, expected: str) -> None:
    assert product_lookup.name_candidate(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "quiero auriculares para viajar",
        "¿hay stock del primero?",
        "Quiero una notebook",
        "algo de hasta 200 USD",
        "hola",
        "",
        "el más barato de los tres",
    ],
)
def test_a_message_without_a_product_name_has_no_candidate(message: str) -> None:
    # Pide dos palabras con mayúscula: así la mayúscula del principio de la
    # oración y un precio con moneda no cuentan como nombre.
    assert product_lookup.name_candidate(message) is None


def test_the_injected_result_brings_the_product(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = product_lookup.lookup_message(catalog_connection, "¿tenés el Nova Vision 24?")

    assert result["found"] is True
    assert result["products"][0]["name"] == "Nova Vision 24"
    assert "El sistema buscó" in result["source"]


def test_the_injected_result_of_a_product_that_does_not_exist_says_so(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Así una afirmación de ausencia también queda respaldada por una consulta.
    result = product_lookup.lookup_message(catalog_connection, "¿tenés el iPhone 15 Pro?")

    assert result["found"] is False
    assert result["searched"] == "iPhone 15 Pro"
    assert "Ningún producto activo del catálogo se llama 'iPhone 15 Pro'" in result["message"]
    assert result["products"] == []


@pytest.mark.parametrize(
    "message", ["quiero auriculares para viajar", "hola", "¿hay stock del primero?"]
)
def test_nothing_is_injected_when_no_product_was_named(
    catalog_connection: sqlite3.Connection, message: str
) -> None:
    assert product_lookup.lookup_message(catalog_connection, message) is None


def test_the_injected_result_does_not_carry_the_quantity_of_stock(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Misma regla que las herramientas: el número solo de check_availability.
    result = product_lookup.lookup_message(catalog_connection, "el Nova Vision 24")

    assert "available_qty" not in result["products"][0]
    assert result["products"][0]["in_stock"] is True


def test_the_lookup_is_not_a_tool_of_the_schema() -> None:
    from backend import tool_schemas

    # La corre el sistema, no el modelo: no se le ofrece como herramienta.
    assert product_lookup.TOOL_NAME not in tool_schemas.TOOL_NAMES
