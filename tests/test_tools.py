"""Tests de backend/tools.py: las seis herramientas sobre la base de prueba."""

from __future__ import annotations

import sqlite3

import pytest

from backend import catalog, tools


def test_searching_by_category_returns_the_products(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, category="Monitors")

    assert result["found"] is True
    assert {product["name"] for product in result["products"]} == {
        "Nova Vision 24",
        "Flux Vision 27",
    }


def test_searching_by_use_case_returns_the_products(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, recommended_for="office work")

    assert {product["name"] for product in result["products"]} == {
        "Nova Vision 24",
        "Nova Sound Pro",
    }


def test_a_search_without_results_says_so_explicitly(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, category="Monitors", max_price=1)

    assert result["found"] is False
    assert result["total"] == 0
    assert result["products"] == []
    assert "No hay productos" in result["message"]


def test_a_search_reports_the_total_without_paginating(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, limit=1)

    assert result["returned"] == 1
    assert result["total"] == 4


@pytest.mark.parametrize(
    ("limit", "expected"), [(0, 1), (-5, 1), (tools.MAX_SEARCH_LIMIT + 50, 4)]
)
def test_a_search_keeps_the_limit_inside_the_allowed_range(
    catalog_connection: sqlite3.Connection, limit: int, expected: int
) -> None:
    result = tools.search_products(catalog_connection, limit=limit)

    assert result["returned"] == expected


def test_a_search_brings_the_use_case_to_justify_the_recommendation(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, search="Nova Vision")

    assert result["products"][0]["recommended_for"] == "office work; programming"


def test_the_details_bring_the_specifications(catalog_connection: sqlite3.Connection) -> None:
    result = tools.get_product_details(catalog_connection, "MN-MON-0001")

    assert result["found"] is True
    assert len(result["product"]["specifications"]) == 2


def test_the_details_keep_the_literal_none_of_a_specification(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_product_details(catalog_connection, "MN-HDP-0001")

    values = {
        specification["attribute_name"]: specification["value_text"]
        for specification in result["product"]["specifications"]
    }
    # "None" significa que el producto no tiene la característica.
    assert values["Water Resistance"] == "None"


def test_the_details_report_a_missing_price_as_null(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_product_details(catalog_connection, "MN-HDP-0003")

    assert result["product"]["current_price"] is None


def test_the_availability_adds_up_the_warehouses(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.check_availability(catalog_connection, "MN-MON-0001")

    assert result["available_qty"] == 10
    assert result["in_stock"] is True
    assert "10 unidades" in result["message"]


def test_the_availability_of_a_product_without_stock_says_there_is_none(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.check_availability(catalog_connection, "MN-MON-0002")

    assert result["available_qty"] == 0
    assert result["in_stock"] is False
    assert "No hay stock" in result["message"]


def test_the_availability_of_a_product_without_inventory_is_zero(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.check_availability(catalog_connection, "MN-HDP-0003")

    assert result["available_qty"] == 0
    assert result["in_stock"] is False


def test_comparing_two_products_returns_their_comparable_data(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-HDP-0001"])

    assert [product["name"] for product in result["products"]] == [
        "Nova Vision 24",
        "Nova Sound Pro",
    ]
    assert result["products"][0]["current_price"] == 468.62


def test_comparing_products_only_uses_the_shared_specifications(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-HDP-0001"])

    # No comparten ningún atributo: uno tiene Display y el otro Audio.
    assert result["shared_specifications"] == []


def test_comparing_products_keeps_the_value_of_each_one(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-MON-0002"])

    assert result["products"][1]["current_price"] == 700.0


@pytest.mark.parametrize(
    "product_ids",
    [[], ["MN-MON-0001"], ["MN-MON-0001", "MN-MON-0002", "MN-HDP-0001", "MN-HDP-0002"]],
)
def test_comparing_the_wrong_amount_of_products_is_rejected(
    catalog_connection: sqlite3.Connection, product_ids: list[str]
) -> None:
    with pytest.raises(tools.ToolArgumentError) as error:
        tools.compare_products(catalog_connection, product_ids)

    assert "entre 2 y 3" in str(error.value)


def test_the_related_products_come_ordered_by_strength(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(catalog_connection, "MN-MON-0001")

    strengths = [item["strength"] for item in result["related"]]
    assert strengths == sorted(strengths, reverse=True)


def test_the_related_products_can_be_filtered_by_type(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(
        catalog_connection, "MN-MON-0001", relation_type="accessory_for"
    )

    assert result["count"] == 1
    assert result["related"][0]["product"]["name"] == "Nova Sound Pro"


def test_a_product_without_relations_says_so_explicitly(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(catalog_connection, "MN-HDP-0003")

    assert result["found"] is False
    assert result["related"] == []
    assert "no tiene productos relacionados" in result["message"]


def test_a_relation_type_without_results_says_so_explicitly(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(
        catalog_connection, "MN-MON-0002", relation_type="accessory_for"
    )

    assert result["found"] is False
    assert "accessory_for" in result["message"]


def test_the_categories_come_grouped_with_their_subcategories(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.list_categories(catalog_connection)

    assert result["found"] is True
    assert result["categories"] == [
        {"category": "Headphones", "subcategories": ["Gaming"]},
        {"category": "Monitors", "subcategories": ["Gaming", "Office"]},
    ]


def test_a_product_that_does_not_exist_is_not_invented(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(catalog.ProductNotFoundError):
        tools.get_product_details(catalog_connection, "MN-NO-EXISTE")


def test_the_availability_of_a_product_that_does_not_exist_is_not_invented(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(catalog.ProductNotFoundError):
        tools.check_availability(catalog_connection, "MN-NO-EXISTE")
