"""Tests de backend/tool_arguments.py: lo que manda el modelo cuando no respeta el esquema."""

from __future__ import annotations

from typing import Any

import pytest

from backend import tool_arguments
from backend.tools import ToolArgumentError

# Los parámetros de search_products, como los declara el esquema del modelo.
SEARCH_PROPERTIES: dict[str, Any] = {
    "category": {"type": "string"},
    "brand": {"type": "string"},
    "min_price": {"type": "number"},
    "max_price": {"type": "number"},
    "recommended_for": {"type": "string"},
    "search": {"type": "string"},
    "limit": {"type": "integer"},
}


@pytest.mark.parametrize(
    "value", ["null", "NULL", "Null", "none", "None", "NONE", "undefined", "nil", "", "   "]
)
def test_the_words_with_which_the_model_says_nothing_are_absent(value: str) -> None:
    assert tool_arguments.is_absent(value) is True


def test_a_null_is_absent() -> None:
    assert tool_arguments.is_absent(None) is True


@pytest.mark.parametrize("value", ["Monitors", "office work", 0, 0.0, False, []])
def test_a_real_value_is_not_absent(value: Any) -> None:
    # El 0 y el False son valores, no ausencias.
    assert tool_arguments.is_absent(value) is False


@pytest.mark.parametrize(
    "value", ["null", "NULL", "none", "undefined", "nil", "", "   ", None]
)
def test_an_optional_argument_that_says_nothing_is_dropped(value: Any) -> None:
    # Así es como falla el modelo chico: manda la palabra en vez de omitir.
    normalized = tool_arguments.normalize_arguments(
        "search_products", SEARCH_PROPERTIES, {"category": "Monitors", "brand": value}
    )

    assert normalized == {"category": "Monitors"}


def test_a_whole_invocation_of_nulls_is_left_with_nothing() -> None:
    # El caso real: el modelo manda todos los opcionales en 'null'.
    normalized = tool_arguments.normalize_arguments(
        "search_products",
        SEARCH_PROPERTIES,
        {
            "category": "null",
            "min_price": "null",
            "max_price": "null",
            "recommended_for": "null",
            "search": "null",
        },
    )

    assert normalized == {}


def test_an_integer_that_comes_as_text_is_converted() -> None:
    normalized = tool_arguments.normalize_arguments(
        "search_products", SEARCH_PROPERTIES, {"limit": "5"}
    )

    assert normalized == {"limit": 5}
    assert isinstance(normalized["limit"], int)


def test_a_number_that_comes_as_text_is_converted() -> None:
    normalized = tool_arguments.normalize_arguments(
        "search_products", SEARCH_PROPERTIES, {"max_price": "200"}
    )

    assert normalized == {"max_price": 200.0}
    assert isinstance(normalized["max_price"], float)


@pytest.mark.parametrize(("value", "expected"), [("200.50", 200.5), (" 200 ", 200.0)])
def test_a_decimal_that_comes_as_text_is_converted(value: str, expected: float) -> None:
    normalized = tool_arguments.normalize_arguments(
        "search_products", SEARCH_PROPERTIES, {"max_price": value}
    )

    assert normalized["max_price"] == expected


def test_an_integer_that_comes_with_decimals_is_truncated() -> None:
    normalized = tool_arguments.normalize_arguments(
        "search_products", SEARCH_PROPERTIES, {"limit": "5.0"}
    )

    assert normalized == {"limit": 5}


def test_a_number_that_already_comes_as_a_number_is_left_alone() -> None:
    normalized = tool_arguments.normalize_arguments(
        "search_products", SEARCH_PROPERTIES, {"max_price": 200, "limit": 3}
    )

    assert normalized == {"max_price": 200.0, "limit": 3}


def test_the_text_arguments_pass_through_untouched() -> None:
    arguments = {"category": "Monitors", "recommended_for": "office work"}

    assert tool_arguments.normalize_arguments(
        "search_products", SEARCH_PROPERTIES, arguments
    ) == arguments


@pytest.mark.parametrize("value", ["barato", "doscientos", "200 USD", "$200"])
def test_a_number_that_is_not_a_number_explains_the_problem(value: str) -> None:
    with pytest.raises(ToolArgumentError) as error:
        tool_arguments.normalize_arguments(
            "search_products", SEARCH_PROPERTIES, {"max_price": value}
        )

    assert "max_price" in str(error.value)
    # El mensaje empieza por qué hacer: el modelo lo lee para corregirse.
    assert str(error.value).startswith("Volvé a invocar")
    assert "sin comillas y sin la moneda" in str(error.value)


def test_a_limit_that_is_not_a_number_explains_the_problem() -> None:
    with pytest.raises(ToolArgumentError) as error:
        tool_arguments.normalize_arguments(
            "search_products", SEARCH_PROPERTIES, {"limit": "todos"}
        )

    assert str(error.value).startswith("Volvé a invocar")
    assert "número entero" in str(error.value)


@pytest.mark.parametrize("parameter", ["limit", "max_price"])
def test_a_boolean_is_not_taken_as_a_number(parameter: str) -> None:
    # True valdría 1, y eso sería inventarle un límite o un precio al usuario.
    with pytest.raises(ToolArgumentError):
        tool_arguments.normalize_arguments(
            "search_products", SEARCH_PROPERTIES, {parameter: True}
        )


def test_an_argument_without_a_declared_type_passes_through() -> None:
    normalized = tool_arguments.normalize_arguments(
        "una_tool", {"algo": {}}, {"algo": "un valor"}
    )

    assert normalized == {"algo": "un valor"}


# El parámetro de compare_products, como lo declara el esquema.
ARRAY_PROPERTIES: dict[str, Any] = {"product_ids": {"type": "array"}}


def test_a_list_that_already_is_a_list_passes_through() -> None:
    normalized = tool_arguments.normalize_arguments(
        "compare_products", ARRAY_PROPERTIES, {"product_ids": ["MN-MON-0001", "MN-MON-0002"]}
    )

    assert normalized == {"product_ids": ["MN-MON-0001", "MN-MON-0002"]}


def test_a_list_that_comes_as_text_is_converted() -> None:
    # Lo que mandó el modelo: la lista escrita, con comillas simples adentro.
    normalized = tool_arguments.normalize_arguments(
        "compare_products",
        ARRAY_PROPERTIES,
        {"product_ids": "['MN-HDP-0001', 'MN-HDP-0009']"},
    )

    assert normalized == {"product_ids": ["MN-HDP-0001", "MN-HDP-0009"]}


@pytest.mark.parametrize(
    "value",
    [
        '["MN-HDP-0001", "MN-HDP-0009"]',
        "['MN-HDP-0001','MN-HDP-0009']",
        "MN-HDP-0001, MN-HDP-0009",
        "[MN-HDP-0001, MN-HDP-0009]",
    ],
)
def test_a_list_is_read_however_the_model_wrote_it(value: str) -> None:
    normalized = tool_arguments.normalize_arguments(
        "compare_products", ARRAY_PROPERTIES, {"product_ids": value}
    )

    assert normalized == {"product_ids": ["MN-HDP-0001", "MN-HDP-0009"]}


def test_a_single_identifier_becomes_a_list_of_one() -> None:
    # Así la herramienta puede decir cuántos esperaba en vez de fallar por el
    # tipo del argumento.
    normalized = tool_arguments.normalize_arguments(
        "compare_products", ARRAY_PROPERTIES, {"product_ids": "MN-HDP-0001"}
    )

    assert normalized == {"product_ids": ["MN-HDP-0001"]}


def test_the_empty_pieces_of_a_list_are_dropped() -> None:
    normalized = tool_arguments.normalize_arguments(
        "compare_products", ARRAY_PROPERTIES, {"product_ids": "['MN-HDP-0001', ]"}
    )

    assert normalized == {"product_ids": ["MN-HDP-0001"]}


def test_an_invocation_without_arguments_stays_empty() -> None:
    assert tool_arguments.normalize_arguments("search_products", SEARCH_PROPERTIES, {}) == {}
