"""Tests de backend/search_filters.py: revisar los filtros y explicar una búsqueda vacía."""

from __future__ import annotations

import sqlite3

import pytest

from backend import search_filters


@pytest.mark.parametrize("value", ["Headphones", "headphones", "HEADPHONES", " Headphones "])
def test_a_value_of_the_catalog_is_valid(value: str) -> None:
    assert search_filters.is_valid(value, ["Headphones", "Monitors"]) is True


@pytest.mark.parametrize("value", ["Earphones", "Head phones", ""])
def test_a_value_that_is_not_in_the_catalog_is_invalid(value: str) -> None:
    assert search_filters.is_valid(value, ["Headphones", "Monitors"]) is False


def test_filters_that_serve_have_no_problems(catalog_connection: sqlite3.Connection) -> None:
    problems = search_filters.filter_problems(
        catalog_connection, category="Monitors", recommended_for="gaming", max_price=500
    )

    assert problems == []


def test_filters_that_serve_do_not_produce_an_error(
    catalog_connection: sqlite3.Connection,
) -> None:
    assert (
        search_filters.filter_error(catalog_connection, category="Monitors", max_price=500)
        is None
    )


def test_a_search_without_filters_has_no_problems(
    catalog_connection: sqlite3.Connection,
) -> None:
    assert search_filters.filter_problems(catalog_connection) == []


def test_an_equal_price_range_is_one_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    problems = search_filters.filter_problems(
        catalog_connection, min_price=200, max_price=200
    )

    assert len(problems) == 1
    assert "no pueden ser iguales" in problems[0]


def test_the_equal_price_problem_says_what_to_send_instead(
    catalog_connection: sqlite3.Connection,
) -> None:
    problems = search_filters.filter_problems(
        catalog_connection, min_price=200, max_price=200
    )

    assert "solo max_price" in problems[0]
    # El valor va sin decimales de más: llegó 200, no 200.0.
    assert "llegaron en 200:" in problems[0]


def test_a_real_price_range_is_not_a_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    assert search_filters.filter_problems(
        catalog_connection, min_price=100, max_price=200
    ) == []


def test_a_category_that_does_not_exist_is_a_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    problems = search_filters.filter_problems(catalog_connection, category="Earphones")

    assert len(problems) == 1
    assert "'Earphones' no existe" in problems[0]


def test_the_category_problem_carries_the_valid_values(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Los valores van en el mensaje para que el modelo corrija en el mismo paso.
    problems = search_filters.filter_problems(catalog_connection, category="Earphones")

    assert "Headphones, Monitors" in problems[0]


def test_a_use_case_that_does_not_exist_is_a_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    problems = search_filters.filter_problems(
        catalog_connection, recommended_for="video conferencing"
    )

    assert "'video conferencing' no existe" in problems[0]
    assert "office work" in problems[0]


def test_the_use_case_problem_says_to_omit_the_parameter(
    catalog_connection: sqlite3.Connection,
) -> None:
    problems = search_filters.filter_problems(
        catalog_connection, recommended_for="video conferencing"
    )

    assert "no mandes recommended_for" in problems[0]


def test_a_use_case_that_does_not_exist_in_that_category_is_a_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Los dos valores existen, pero 'gaming' es de Monitors: juntos no traen
    # nada, y es el error que devolvía cero resultados.
    problems = search_filters.filter_problems(
        catalog_connection, category="Headphones", recommended_for="gaming"
    )

    assert len(problems) == 1
    assert "'Headphones' no tiene productos para 'gaming'" in problems[0]


def test_the_combination_problem_returns_the_use_cases_of_that_category(
    catalog_connection: sqlite3.Connection,
) -> None:
    problems = search_filters.filter_problems(
        catalog_connection, category="Headphones", recommended_for="gaming"
    )

    # Los de esa categoría, no los del catálogo entero.
    assert "casual listening, office work, travel" in problems[0]
    assert "programming" not in problems[0]


def test_the_combination_problem_says_what_to_do(
    catalog_connection: sqlite3.Connection,
) -> None:
    problems = search_filters.filter_problems(
        catalog_connection, category="Headphones", recommended_for="gaming"
    )

    assert "buscá sin recommended_for" in problems[0]


def test_a_combination_that_exists_is_not_a_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    assert search_filters.filter_problems(
        catalog_connection, category="Headphones", recommended_for="travel"
    ) == []


@pytest.mark.parametrize("category", ["headphones", "HEADPHONES"])
def test_the_combination_is_checked_ignoring_the_case(
    catalog_connection: sqlite3.Connection, category: str
) -> None:
    assert search_filters.filter_problems(
        catalog_connection, category=category, recommended_for="travel"
    ) == []


def test_a_use_case_without_a_category_is_not_checked_against_one(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Sin categoría, cualquier caso de uso del catálogo sirve.
    assert search_filters.filter_problems(catalog_connection, recommended_for="gaming") == []


def test_an_invalid_category_does_not_add_a_combination_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    # La categoría ya está reportada: decirle además que no tiene ese caso de
    # uso lo mandaría a corregir algo que no es el problema.
    problems = search_filters.filter_problems(
        catalog_connection, category="Earphones", recommended_for="travel"
    )

    assert len(problems) == 1
    assert "'Earphones' no existe" in problems[0]


def test_a_use_case_that_is_only_part_of_a_real_one_is_a_problem(
    catalog_connection: sqlite3.Connection,
) -> None:
    # El filtro acepta el valor exacto del catálogo, no un pedazo.
    problems = search_filters.filter_problems(catalog_connection, recommended_for="office")

    assert problems


def test_every_problem_comes_back_in_the_same_pass(
    catalog_connection: sqlite3.Connection,
) -> None:
    problems = search_filters.filter_problems(
        catalog_connection,
        category="Earphones",
        recommended_for="video conferencing",
        min_price=200,
        max_price=200,
    )

    assert len(problems) == 3


def test_the_error_joins_every_problem(catalog_connection: sqlite3.Connection) -> None:
    error = search_filters.filter_error(
        catalog_connection, category="Earphones", min_price=200, max_price=200
    )

    assert "No se puede buscar con esos filtros" in error
    assert "no pueden ser iguales" in error
    assert "'Earphones' no existe" in error
    assert error.endswith("Corregí lo que esté mal y buscá de nuevo.")


def test_an_empty_result_reports_only_the_filters_that_were_used(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = search_filters.empty_result(
        catalog_connection, {"category": "Monitors", "brand": None, "max_price": 1}
    )

    assert result["filters_used"] == {"category": "Monitors", "max_price": 1}


def test_an_empty_result_does_not_invent_products(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = search_filters.empty_result(catalog_connection, {"category": "Monitors"})

    assert result["found"] is False
    assert result["total"] == 0
    assert result["products"] == []


def test_an_empty_result_asks_to_retry_before_giving_up(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = search_filters.empty_result(catalog_connection, {"category": "Monitors"})

    assert "no le digas al usuario que no hay nada sin volver a intentar" in result["message"]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"category": "Monitors"}, "valid_categories"),
        ({"recommended_for": "gaming"}, "valid_recommended_for"),
        ({"search": "4K"}, "note_about_search"),
    ],
)
def test_an_empty_result_helps_with_the_filter_that_was_used(
    catalog_connection: sqlite3.Connection, filters: dict[str, str], expected: str
) -> None:
    assert expected in search_filters.empty_result(catalog_connection, filters)


def test_an_empty_result_offers_the_use_cases_of_the_category_that_was_used(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Con categoría, los del catálogo entero lo mandarían a combinar de nuevo
    # dos valores que juntos no traen nada.
    result = search_filters.empty_result(
        catalog_connection, {"category": "Headphones", "recommended_for": "travel"}
    )

    assert result["valid_recommended_for"] == ["casual listening", "office work", "travel"]


def test_an_empty_result_without_a_category_offers_every_use_case(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = search_filters.empty_result(catalog_connection, {"recommended_for": "travel"})

    assert "programming" in result["valid_recommended_for"]


@pytest.mark.parametrize(
    "unexpected", ["valid_categories", "valid_recommended_for", "note_about_search"]
)
def test_an_empty_result_does_not_help_with_a_filter_that_was_not_used(
    catalog_connection: sqlite3.Connection, unexpected: str
) -> None:
    # Cada lista ocupa lugar en la ventana de contexto del modelo.
    result = search_filters.empty_result(catalog_connection, {"brand": "NovaTech"})

    assert unexpected not in result
