"""Tests de backend/tool_schemas.py: el formato que recibe el modelo."""

from __future__ import annotations

from typing import Any

import pytest

from backend import catalog_sql, tool_router, tool_schemas

EXPECTED_NAMES = [
    "search_products",
    "get_product_details",
    "check_availability",
    "compare_products",
    "get_related_products",
    "list_categories",
]


def test_there_are_six_tools() -> None:
    assert len(tool_schemas.TOOL_SCHEMAS) == 6


def test_the_tools_are_the_expected_ones() -> None:
    assert list(tool_schemas.TOOL_NAMES) == EXPECTED_NAMES


@pytest.mark.parametrize("schema", tool_schemas.TOOL_SCHEMAS, ids=EXPECTED_NAMES)
def test_every_tool_follows_the_ollama_format(schema: dict[str, Any]) -> None:
    assert schema["type"] == "function"
    assert set(schema["function"]) == {"name", "description", "parameters"}
    assert schema["function"]["parameters"]["type"] == "object"


@pytest.mark.parametrize("schema", tool_schemas.TOOL_SCHEMAS, ids=EXPECTED_NAMES)
def test_every_tool_explains_what_it_does(schema: dict[str, Any]) -> None:
    # La descripción es lo único que el modelo tiene para elegir la herramienta.
    assert len(schema["function"]["description"]) > 60


@pytest.mark.parametrize("schema", tool_schemas.TOOL_SCHEMAS, ids=EXPECTED_NAMES)
def test_every_parameter_has_a_type_and_a_description(schema: dict[str, Any]) -> None:
    for parameter in schema["function"]["parameters"]["properties"].values():
        assert "type" in parameter
        assert parameter.get("description")


@pytest.mark.parametrize("schema", tool_schemas.TOOL_SCHEMAS, ids=EXPECTED_NAMES)
def test_the_required_parameters_exist_in_the_schema(schema: dict[str, Any]) -> None:
    parameters = schema["function"]["parameters"]

    assert set(parameters["required"]) <= set(parameters["properties"])


@pytest.mark.parametrize("schema", tool_schemas.TOOL_SCHEMAS, ids=EXPECTED_NAMES)
def test_every_tool_has_an_implementation(schema: dict[str, Any]) -> None:
    assert schema["function"]["name"] in tool_router.IMPLEMENTATIONS


def test_the_search_tool_filters_by_use_case() -> None:
    properties = tool_schemas.SEARCH_PRODUCTS_SCHEMA["function"]["parameters"]["properties"]

    assert "recommended_for" in properties
    assert set(properties) == {
        "category",
        "brand",
        "min_price",
        "max_price",
        "recommended_for",
        "search",
        "limit",
    }


def test_the_search_tool_has_no_required_parameters() -> None:
    assert tool_schemas.SEARCH_PRODUCTS_SCHEMA["function"]["parameters"]["required"] == []


@pytest.mark.parametrize(
    "name", ["get_product_details", "check_availability", "get_related_products"]
)
def test_the_tools_that_need_a_product_require_its_identifier(name: str) -> None:
    assert tool_router.SCHEMA_BY_NAME[name]["required"] == ["product_id"]


def test_the_relation_type_offers_the_three_types_of_the_dataset() -> None:
    properties = tool_schemas.GET_RELATED_PRODUCTS_SCHEMA["function"]["parameters"]["properties"]

    assert properties["relation_type"]["enum"] == list(catalog_sql.RELATION_TYPES)


def test_the_comparison_takes_a_list_of_identifiers() -> None:
    properties = tool_schemas.COMPARE_PRODUCTS_SCHEMA["function"]["parameters"]["properties"]

    assert properties["product_ids"]["type"] == "array"
    assert properties["product_ids"]["items"]["type"] == "string"


def test_listing_the_categories_takes_no_parameters() -> None:
    parameters = tool_schemas.LIST_CATEGORIES_SCHEMA["function"]["parameters"]

    assert parameters["properties"] == {}
    assert parameters["required"] == []


def test_the_identifier_description_warns_against_inventing_one() -> None:
    assert "no lo inventes" in tool_schemas.PRODUCT_ID_DESCRIPTION


def test_the_schemas_do_not_carry_catalog_data() -> None:
    # Los ejemplos de las descripciones son formatos, no datos de productos.
    text = str(tool_schemas.TOOL_SCHEMAS)

    assert "current_price" not in text
    assert "468.62" not in text
