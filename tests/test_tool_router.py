"""Tests de backend/tool_router.py: validación de argumentos y ruteo."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend import db, tool_router, tool_schemas

EVERY_TOOL = [
    ("search_products", {"category": "Monitors"}),
    ("get_product_details", {"product_id": "MN-MON-0001"}),
    ("check_availability", {"product_id": "MN-MON-0001"}),
    ("compare_products", {"product_ids": ["MN-MON-0001", "MN-MON-0002"]}),
    ("get_related_products", {"product_id": "MN-MON-0001"}),
    ("list_categories", {}),
]


def test_every_tool_of_the_schema_has_an_implementation() -> None:
    assert set(tool_router.IMPLEMENTATIONS) == set(tool_schemas.TOOL_NAMES)


def test_there_is_no_implementation_without_its_schema() -> None:
    assert set(tool_router.IMPLEMENTATIONS) <= set(tool_router.SCHEMA_BY_NAME)


def test_running_a_tool_by_name_returns_its_result(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection, "check_availability", {"product_id": "MN-MON-0001"}
    )

    assert result["available_qty"] == 10


@pytest.mark.parametrize(("name", "arguments"), EVERY_TOOL)
def test_every_tool_can_be_reached_by_name(
    catalog_connection: sqlite3.Connection, name: str, arguments: dict[str, object]
) -> None:
    result = tool_router.run_tool(catalog_connection, name, arguments)

    assert "error" not in result


@pytest.mark.parametrize(("name", "arguments"), EVERY_TOOL)
def test_every_result_is_serializable_for_the_model(
    catalog_connection: sqlite3.Connection, name: str, arguments: dict[str, object]
) -> None:
    result = tool_router.run_tool(catalog_connection, name, arguments)

    assert json.loads(json.dumps(result, default=str))


def test_running_an_unknown_tool_explains_which_ones_exist(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(catalog_connection, "comprar_todo", {})

    assert result["found"] is False
    assert "no existe" in result["error"]
    assert "search_products" in result["error"]


def test_validating_an_unknown_tool_is_rejected() -> None:
    with pytest.raises(tool_router.tools.UnknownToolError):
        tool_router.validate_arguments("comprar_todo", {})


def test_an_unknown_argument_explains_the_valid_ones() -> None:
    with pytest.raises(tool_router.tools.ToolArgumentError) as error:
        tool_router.validate_arguments("search_products", {"categoria": "Monitors"})

    assert "no acepta el argumento 'categoria'" in str(error.value)
    assert "category" in str(error.value)


def test_a_missing_required_argument_says_which_one_it_is() -> None:
    with pytest.raises(tool_router.tools.ToolArgumentError) as error:
        tool_router.validate_arguments("get_product_details", {})

    assert "necesita el argumento 'product_id'" in str(error.value)


@pytest.mark.parametrize("empty", ["", None])
def test_the_empty_optional_arguments_are_dropped(empty: str | None) -> None:
    # El modelo manda cadenas vacías para los filtros que no usa.
    cleaned = tool_router.validate_arguments(
        "search_products", {"category": "Monitors", "brand": empty}
    )

    assert cleaned == {"category": "Monitors"}


def test_an_empty_required_argument_is_rejected() -> None:
    with pytest.raises(tool_router.tools.ToolArgumentError):
        tool_router.validate_arguments("get_product_details", {"product_id": ""})


def test_a_tool_without_parameters_accepts_an_empty_call() -> None:
    assert tool_router.validate_arguments("list_categories", {}) == {}


def test_a_tool_without_parameters_rejects_an_argument() -> None:
    with pytest.raises(tool_router.tools.ToolArgumentError) as error:
        tool_router.validate_arguments("list_categories", {"category": "Monitors"})

    assert "ninguno" in str(error.value)


def test_the_valid_arguments_pass_through_untouched() -> None:
    arguments = {"category": "Monitors", "max_price": 500, "limit": 3}

    assert tool_router.validate_arguments("search_products", arguments) == arguments


def test_asking_for_a_product_that_does_not_exist_does_not_invent_it(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection, "get_product_details", {"product_id": "MN-NO-EXISTE"}
    )

    assert result["found"] is False
    assert "No existe el producto" in result["error"]
    assert "product" not in result


def test_an_invalid_relation_type_explains_the_valid_ones(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        "get_related_products",
        {"product_id": "MN-MON-0001", "relation_type": "parecido"},
    )

    assert "alternative_to" in result["error"]


def test_an_invalid_price_filter_explains_the_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection, "search_products", {"min_price": 500, "max_price": 100}
    )

    assert result["found"] is False
    assert "mínimo" in result["error"]


def test_a_business_rule_of_a_tool_travels_as_an_error(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection, "compare_products", {"product_ids": ["MN-MON-0001"]}
    )

    assert result["found"] is False
    assert "entre 2 y 3" in result["error"]


def test_an_argument_of_the_wrong_type_does_not_break_the_conversation(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Pase lo que pase, el modelo recibe un resultado que puede leer.
    result = tool_router.run_tool(
        catalog_connection, "compare_products", {"product_ids": "MN-MON-0001"}
    )

    assert result["found"] is False
    assert result["error"]


def test_a_database_without_schema_answers_with_an_actionable_message(tmp_path: Path) -> None:
    connection = db.connect(tmp_path / "vacia.db")
    try:
        result = tool_router.run_tool(connection, "list_categories", {})
    finally:
        connection.close()

    assert result["found"] is False
    assert "load_dataset.py" in result["error"]
