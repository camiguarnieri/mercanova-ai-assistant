"""Tests de backend/catalog_sql.py: escapado de comodines y armado del WHERE."""

from __future__ import annotations

import pytest

from backend import catalog_sql


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("monitor", "%monitor%"),
        ("  monitor  ", "%monitor%"),
        ("50%", r"%50\%%"),
        ("a_b", r"%a\_b%"),
        ("c:\\temp", r"%c:\\temp%"),
    ],
)
def test_like_pattern_escapes_the_wildcards(text: str, expected: str) -> None:
    assert catalog_sql.like_pattern(text) == expected


def test_without_filters_only_the_active_products_are_required() -> None:
    where, parameters = catalog_sql.build_filters()

    assert where == "WHERE p.active = 1"
    assert parameters == []


def test_without_any_condition_there_is_no_where_clause() -> None:
    where, parameters = catalog_sql.build_filters(only_active=False)

    assert where == ""
    assert parameters == []


def test_the_category_filter_travels_as_a_parameter() -> None:
    where, parameters = catalog_sql.build_filters(category="Monitors", only_active=False)

    # El valor nunca se interpola en el SQL.
    assert "Monitors" not in where
    assert parameters == ["Monitors"]


def test_the_brand_filter_looks_for_the_name_and_the_identifier() -> None:
    where, parameters = catalog_sql.build_filters(brand="NovaTech", only_active=False)

    assert "p.brand_id" in where
    assert parameters == ["NovaTech", "NovaTech"]


def test_the_search_filter_covers_every_text_field() -> None:
    where, parameters = catalog_sql.build_filters(search="240 Hz", only_active=False)

    assert where.count("LIKE ? ESCAPE") == len(catalog_sql.SEARCH_FIELDS)
    assert parameters == ["%240 Hz%"] * len(catalog_sql.SEARCH_FIELDS)


@pytest.mark.parametrize("field", ["p.name", "p.description", "p.recommended_for", "p.tags"])
def test_the_search_filter_names_the_use_case_fields(field: str) -> None:
    where, _ = catalog_sql.build_filters(search="gaming", only_active=False)

    assert field in where


def test_the_recommended_for_filter_compares_by_substring() -> None:
    where, parameters = catalog_sql.build_filters(
        recommended_for="office work", only_active=False
    )

    # La columna trae varios usos separados por punto y coma.
    assert where == "WHERE p.recommended_for LIKE ? ESCAPE '\\'"
    assert parameters == ["%office work%"]


def test_the_recommended_for_filter_escapes_the_wildcards() -> None:
    _, parameters = catalog_sql.build_filters(recommended_for="100%", only_active=False)

    assert parameters == [r"%100\%%"]


@pytest.mark.parametrize("recommended_for", ["", "   "])
def test_an_empty_recommended_for_does_not_add_a_condition(recommended_for: str) -> None:
    where, parameters = catalog_sql.build_filters(
        recommended_for=recommended_for, only_active=False
    )

    assert where == ""
    assert parameters == []


@pytest.mark.parametrize("search", ["", "   "])
def test_an_empty_search_does_not_add_a_condition(search: str) -> None:
    where, parameters = catalog_sql.build_filters(search=search, only_active=False)

    assert where == ""
    assert parameters == []


def test_a_price_of_zero_is_a_filter_and_not_an_absence() -> None:
    where, parameters = catalog_sql.build_filters(min_price=0, only_active=False)

    assert "pr.current_price >= ?" in where
    assert parameters == [0]


def test_the_conditions_and_the_parameters_keep_the_same_order() -> None:
    where, parameters = catalog_sql.build_filters(
        category="Monitors",
        brand="BR001",
        recommended_for="office work",
        min_price=100,
        max_price=500,
        search="ips",
    )

    assert where.count("?") == len(parameters)
    assert parameters == [
        "Monitors",
        "BR001",
        "BR001",
        "%office work%",
        100,
        500,
        *["%ips%"] * len(catalog_sql.SEARCH_FIELDS),
    ]
