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
]


def test_there_are_five_tools() -> None:
    assert len(tool_schemas.TOOL_SCHEMAS) == 5


def test_the_categories_are_not_a_tool_of_their_own() -> None:
    # Viajan en el enum de search_products: una herramienta para pedirlas no
    # aporta nada y ocupa contexto en cada turno.
    assert "list_categories" not in tool_schemas.TOOL_NAMES


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


# Las descripciones de los parámetros de search_products.
SEARCH_DESCRIPTIONS = {
    name: parameter["description"]
    for name, parameter in tool_schemas.SEARCH_PRODUCTS_SCHEMA["function"]["parameters"][
        "properties"
    ].items()
}


@pytest.mark.parametrize(
    ("parameter", "rule"),
    [
        # Las reglas de cada filtro viven acá y no en el prompt: es lo que el
        # modelo lee mientras arma la invocación.
        ("min_price", "solo si el usuario dijo un piso de precio"),
        ("min_price", "Nunca igual a max_price"),
        ("max_price", "Nunca igual a min_price"),
        ("category", "Solo una de las que enumera este parámetro"),
        ("recommended_for", "omití el parámetro"),
        ("search", "en inglés"),
        ("search", "no es para describir la necesidad del usuario"),
        ("limit", "Por defecto 5"),
    ],
)
def test_the_schema_of_a_filter_carries_its_own_rule(parameter: str, rule: str) -> None:
    assert rule.lower() in SEARCH_DESCRIPTIONS[parameter].lower()


def test_the_search_tool_says_that_it_does_not_return_the_quantity() -> None:
    # Garantía del RF-07: el número de stock solo sale de check_availability.
    description = tool_schemas.SEARCH_PRODUCTS_SCHEMA["function"]["description"]

    assert "no cuántas unidades" in description
    assert "check_availability" in description


def test_the_search_tool_is_also_for_finding_a_product_by_name() -> None:
    # Dijo que no tenía un producto que existe, sin buscarlo.
    description = tool_schemas.SEARCH_PRODUCTS_SCHEMA["function"]["description"]

    assert "del que sabés el nombre" in description


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


def test_the_comparison_schema_says_the_same_amount_as_the_tool() -> None:
    # Si MAX_COMPARE cambia, el texto que lee el modelo tiene que cambiar con él.
    from backend import tools

    description = tool_schemas.COMPARE_PRODUCTS_SCHEMA["function"]["description"]
    assert tools.MAX_COMPARE == 3
    assert "dos o tres productos" in description


def test_the_comparison_schema_says_that_the_identifiers_are_internal() -> None:
    properties = tool_schemas.COMPARE_PRODUCTS_SCHEMA["function"]["parameters"]["properties"]

    assert "no se le preguntan al usuario" in properties["product_ids"]["description"]


def test_the_comparison_schema_says_that_it_trims_instead_of_failing() -> None:
    properties = tool_schemas.COMPARE_PRODUCTS_SCHEMA["function"]["parameters"]["properties"]

    assert "compara los tres primeros" in properties["product_ids"]["description"]


def test_the_comparison_takes_a_list_of_identifiers() -> None:
    properties = tool_schemas.COMPARE_PRODUCTS_SCHEMA["function"]["parameters"]["properties"]

    assert properties["product_ids"]["type"] == "array"
    assert properties["product_ids"]["items"]["type"] == "string"


def test_the_identifier_description_warns_against_inventing_one() -> None:
    assert "no lo inventes" in tool_schemas.PRODUCT_ID_DESCRIPTION


def test_the_schemas_do_not_carry_catalog_data() -> None:
    # Los ejemplos de las descripciones son formatos, no datos de productos.
    text = str(tool_schemas.TOOL_SCHEMAS)

    assert "current_price" not in text
    assert "468.62" not in text
