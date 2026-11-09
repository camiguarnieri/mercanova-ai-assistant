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
    assert result["error"].startswith("Volvé a intentar")
    assert "search_products" in result["error"]


def test_validating_an_unknown_tool_is_rejected() -> None:
    with pytest.raises(tool_router.tools.UnknownToolError):
        tool_router.validate_arguments("comprar_todo", {})


def test_an_unknown_argument_explains_the_valid_ones() -> None:
    with pytest.raises(tool_router.tools.ToolArgumentError) as error:
        tool_router.validate_arguments("search_products", {"categoria": "Monitors"})

    assert "sin el argumento 'categoria'" in str(error.value)
    assert "category" in str(error.value)


def test_a_missing_required_argument_says_which_one_it_is() -> None:
    with pytest.raises(tool_router.tools.ToolArgumentError) as error:
        tool_router.validate_arguments("get_product_details", {})

    assert "con el argumento 'product_id'" in str(error.value)


@pytest.mark.parametrize("empty", ["", None, "null", "NULL", "none", "undefined", "nil"])
def test_the_empty_optional_arguments_are_dropped(empty: str | None) -> None:
    # El modelo manda cadenas vacías, o la palabra 'null', para los filtros que
    # no usa, en vez de omitirlos.
    cleaned = tool_router.validate_arguments(
        "search_products", {"category": "Monitors", "brand": empty}
    )

    assert cleaned == {"category": "Monitors"}


@pytest.mark.parametrize("empty", ["", "null", "NULL", "undefined", "nil"])
def test_an_empty_required_argument_is_rejected(empty: str) -> None:
    with pytest.raises(tool_router.tools.ToolArgumentError) as error:
        tool_router.validate_arguments("get_product_details", {"product_id": empty})

    # Un obligatorio que llega vacío sí es un error, y dice cuál falta.
    assert "con el argumento 'product_id'" in str(error.value)


def test_the_invocation_full_of_nulls_of_the_model_still_searches(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Lo que mandaba el modelo y rompía la búsqueda: los opcionales en 'null' y
    # los números como texto.
    result = tool_router.run_tool(
        catalog_connection,
        "search_products",
        {
            "category": "null",
            "limit": "5",
            "max_price": "null",
            "min_price": "null",
            "recommended_for": "null",
            "search": "null",
        },
    )

    assert result["found"] is True
    assert "error" not in result


def test_a_numeric_filter_that_comes_as_text_filters_the_same(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection, "search_products", {"max_price": "200", "limit": "5"}
    )

    assert [product["name"] for product in result["products"]] == ["Nova Sound Pro"]


def test_the_numbers_that_come_as_text_are_converted() -> None:
    cleaned = tool_router.validate_arguments(
        "search_products", {"limit": "5", "max_price": "200"}
    )

    assert cleaned == {"limit": 5, "max_price": 200.0}


def test_a_filter_that_is_not_a_number_does_not_break_the_conversation(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection, "search_products", {"max_price": "barato"}
    )

    assert result["found"] is False
    assert "max_price" in result["error"]


def test_the_reported_invocation_comes_back_as_a_correctable_error(
    catalog_connection: sqlite3.Connection,
) -> None:
    # La llamada que reportó cero resultados. El modelo tiene que recibir qué
    # hizo mal, no una excepción ni una lista vacía.
    result = tool_router.run_tool(
        catalog_connection,
        "search_products",
        {
            "max_price": 200,
            "min_price": 200,
            "recommended_for": "video conferencing",
            "search": "auriculares para videollamadas",
            "category": "Headphones",
            "limit": 5,
        },
    )

    assert result["found"] is False
    assert "no pueden ser iguales" in result["error"]


def test_an_invented_use_case_comes_back_with_the_valid_ones(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        "search_products",
        {"category": "Headphones", "recommended_for": "video conferencing"},
    )

    assert result["found"] is False
    assert "office work" in result["error"]


def test_the_reported_invocation_reports_its_three_problems_at_once(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        "search_products",
        {
            "max_price": 200,
            "min_price": 200,
            "recommended_for": "video conferencing",
            "search": "auriculares para videollamadas",
            "category": "Headphones",
            "limit": 5,
        },
    )

    # El precio y el caso de uso, en una sola vuelta al modelo.
    assert "no pueden ser iguales" in result["error"]
    assert "'video conferencing' no existe" in result["error"]


def test_an_invented_identifier_is_not_executed(
    catalog_connection: sqlite3.Connection,
) -> None:
    # La falla reportada: 'MN-DOK-0001' no existe y el modelo lo armó solo.
    result = tool_router.run_tool(
        catalog_connection,
        "check_availability",
        {"product_id": "MN-DOK-0001"},
        known_products=set(),
    )

    assert result["found"] is False
    assert "no salió de ninguna búsqueda de esta conversación" in result["error"]


def test_an_identifier_that_exists_but_was_not_searched_is_not_executed(
    catalog_connection: sqlite3.Connection,
) -> None:
    # MN-MON-0001 existe: la regla es de procedencia, no de existencia.
    result = tool_router.run_tool(
        catalog_connection,
        "check_availability",
        {"product_id": "MN-MON-0001"},
        known_products=set(),
    )

    assert result["found"] is False
    assert "exista o no en el catálogo" in result["error"]
    assert "available_qty" not in result


def test_an_identifier_that_came_from_a_result_is_executed(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        "check_availability",
        {"product_id": "MN-MON-0001"},
        known_products={"MN-MON-0001"},
    )

    assert result["available_qty"] == 10


def test_a_missing_argument_is_reported_before_its_provenance(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Primero se valida la invocación: un 'null' no es un id inventado.
    result = tool_router.run_tool(
        catalog_connection, "check_availability", {"product_id": "null"}, known_products=set()
    )

    assert "con el argumento 'product_id'" in result["error"]


def test_a_search_does_not_need_any_provenance(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Buscar es lo que da los identificadores: no puede depender de tenerlos.
    result = tool_router.run_tool(
        catalog_connection, "search_products", {"category": "Monitors"}, known_products=set()
    )

    assert result["found"] is True


def test_a_comparison_with_one_invented_identifier_is_not_executed(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tool_router.run_tool(
        catalog_connection,
        "compare_products",
        {"product_ids": ["MN-MON-0001", "MN-DOK-0001"]},
        known_products={"MN-MON-0001"},
    )

    assert result["found"] is False
    assert "'MN-DOK-0001'" in result["error"]


def test_the_list_that_comes_as_text_is_compared(
    catalog_connection: sqlite3.Connection,
) -> None:
    # El modelo manda la lista escrita, con comillas simples adentro.
    result = tool_router.run_tool(
        catalog_connection,
        "compare_products",
        {"product_ids": "['MN-MON-0001', 'MN-HDP-0001']"},
        known_products={"MN-MON-0001", "MN-HDP-0001"},
    )

    assert [product["name"] for product in result["products"]] == [
        "Nova Vision 24",
        "Nova Sound Pro",
    ]


def test_the_trace_shows_the_arguments_that_were_used() -> None:
    # En la interfaz se muestra con qué se consultó, no los 'null' de más.
    shown = tool_router.arguments_for_trace(
        "search_products", {"category": "Monitors", "brand": "null", "limit": "5"}
    )

    assert shown == {"category": "Monitors", "limit": 5}


def test_the_trace_of_a_failed_invocation_shows_what_the_model_sent() -> None:
    arguments = {"product_id": "null"}

    assert tool_router.arguments_for_trace("get_product_details", arguments) == arguments


def test_the_trace_of_an_unknown_tool_shows_what_the_model_sent() -> None:
    arguments = {"todo": "sí"}

    assert tool_router.arguments_for_trace("comprar_todo", arguments) == arguments


def test_a_tool_with_every_parameter_optional_accepts_an_empty_call() -> None:
    # search_products se puede invocar sin filtros: trae el catálogo entero.
    assert tool_router.validate_arguments("search_products", {}) == {}


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
    assert result["error"].startswith("Volvé a invocar compare_products")


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
        result = tool_router.run_tool(connection, "search_products", {})
    finally:
        connection.close()

    assert result["found"] is False
    assert "load_dataset.py" in result["error"]
