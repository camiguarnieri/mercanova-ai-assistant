"""Tests de backend/catalog.py: filtros, paginado, stock y especificaciones."""

from __future__ import annotations

import sqlite3

import pytest

from backend import catalog

# Productos activos del catálogo de prueba, ordenados por nombre.
ACTIVE_NAMES = ["Flux Vision 27", "Nova Sound Lite", "Nova Sound Pro", "Nova Vision 24"]


def test_lists_only_the_active_products_by_default(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection)

    assert [item.name for item in page.items] == ACTIVE_NAMES
    assert page.total == 4


def test_can_include_the_products_that_were_discontinued(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, only_active=False)

    assert page.total == 5
    assert "Flux Buds" in [item.name for item in page.items]


def test_filters_by_category(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, category="Monitors")

    assert {item.name for item in page.items} == {"Nova Vision 24", "Flux Vision 27"}


def test_filters_by_category_ignoring_the_case(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, category="monitors")

    assert page.total == 2


def test_filters_by_subcategory(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, subcategory="Office")

    assert [item.name for item in page.items] == ["Nova Vision 24"]


@pytest.mark.parametrize("brand", ["NovaTech", "novatech", "BR001"])
def test_filters_by_brand_name_or_identifier(
    catalog_connection: sqlite3.Connection, brand: str
) -> None:
    page = catalog.list_products(catalog_connection, brand=brand)

    assert page.total == 3


def test_filters_by_minimum_price(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, min_price=500)

    assert [item.name for item in page.items] == ["Flux Vision 27"]


def test_filters_by_maximum_price(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, max_price=200)

    assert [item.name for item in page.items] == ["Nova Sound Pro"]


def test_filters_by_a_price_range(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, min_price=100, max_price=500)

    assert {item.name for item in page.items} == {"Nova Sound Pro", "Nova Vision 24"}


def test_a_price_filter_leaves_out_the_products_without_a_price(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, min_price=0)

    # "Nova Sound Lite" no tiene precio cargado: no se puede afirmar que entre
    # en el rango, así que no se devuelve.
    assert "Nova Sound Lite" not in [item.name for item in page.items]


def test_searches_the_free_text_in_the_name(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, search="vision")

    assert {item.name for item in page.items} == {"Nova Vision 24", "Flux Vision 27"}


def test_searches_the_free_text_in_the_description(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, search="240 Hz")

    assert [item.name for item in page.items] == ["Flux Vision 27"]


def test_searches_the_free_text_in_recommended_for(
    catalog_connection: sqlite3.Connection,
) -> None:
    # "programming" solo está en recommended_for.
    page = catalog.list_products(catalog_connection, search="programming")

    assert [item.name for item in page.items] == ["Nova Vision 24"]


def test_searches_the_free_text_in_the_tags(catalog_connection: sqlite3.Connection) -> None:
    # "noise-cancelling" solo está en tags.
    page = catalog.list_products(catalog_connection, search="noise-cancelling")

    assert [item.name for item in page.items] == ["Nova Sound Pro"]


def test_a_search_by_use_case_finds_the_product_by_its_tags(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, search="gaming")

    assert [item.name for item in page.items] == ["Flux Vision 27"]


def test_filters_by_recommended_for(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, recommended_for="office work")

    assert {item.name for item in page.items} == {"Nova Vision 24", "Nova Sound Pro"}


def test_filters_by_recommended_for_ignoring_the_case(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, recommended_for="OFFICE WORK")

    assert page.total == 2


def test_the_recommended_for_filter_finds_a_use_case_in_the_middle_of_the_list(
    catalog_connection: sqlite3.Connection,
) -> None:
    # En "travel; office work" el uso buscado no es el primero.
    page = catalog.list_products(catalog_connection, recommended_for="travel")

    assert [item.name for item in page.items] == ["Nova Sound Pro"]


def test_the_recommended_for_filter_leaves_out_the_discontinued_products(
    catalog_connection: sqlite3.Connection,
) -> None:
    # "Flux Buds" se recomienda para programming, pero está dado de baja.
    page = catalog.list_products(catalog_connection, recommended_for="programming")

    assert [item.name for item in page.items] == ["Nova Vision 24"]


def test_the_recommended_for_filter_combines_with_the_other_filters(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(
        catalog_connection, recommended_for="office work", category="Headphones"
    )

    assert [item.name for item in page.items] == ["Nova Sound Pro"]


def test_a_recommended_for_without_results_returns_an_empty_page(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, recommended_for="minería de datos")

    assert page.items == []
    assert page.total == 0


@pytest.mark.parametrize("recommended_for", ["%", "_"])
def test_the_recommended_for_filter_does_not_treat_the_wildcards_as_a_pattern(
    catalog_connection: sqlite3.Connection, recommended_for: str
) -> None:
    page = catalog.list_products(catalog_connection, recommended_for=recommended_for)

    assert page.total == 0


def test_the_summary_brings_recommended_for(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, search="Nova Vision")

    assert page.items[0].recommended_for == "office work; programming"


def test_the_summary_does_not_bring_the_tags(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, limit=1)

    # tags queda solo en la ficha completa.
    assert "tags" not in page.items[0].model_dump()


def test_the_detail_brings_the_use_case_fields(catalog_connection: sqlite3.Connection) -> None:
    detail = catalog.get_product(catalog_connection, "MN-MON-0001")

    assert detail.recommended_for == "office work; programming"
    assert detail.tags == "monitor; display; qhd"


def test_a_search_without_results_returns_an_empty_page(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, search="heladera")

    assert page.items == []
    assert page.total == 0
    assert page.has_more is False


@pytest.mark.parametrize("search", ["%", "_", "%%"])
def test_a_search_does_not_treat_the_wildcards_as_a_pattern(
    catalog_connection: sqlite3.Connection, search: str
) -> None:
    page = catalog.list_products(catalog_connection, search=search)

    assert page.total == 0


def test_combines_several_filters(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(
        catalog_connection, category="Headphones", brand="NovaTech", max_price=130
    )

    assert [item.name for item in page.items] == ["Nova Sound Pro"]


def test_the_page_respects_the_limit(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, limit=2)

    assert [item.name for item in page.items] == ACTIVE_NAMES[:2]
    assert page.total == 4
    assert page.has_more is True


def test_the_page_respects_the_offset(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, limit=2, offset=2)

    assert [item.name for item in page.items] == ACTIVE_NAMES[2:]
    assert page.has_more is False


def test_an_offset_beyond_the_total_returns_an_empty_page(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, offset=99)

    assert page.items == []
    assert page.total == 4


def test_the_pages_do_not_repeat_or_lose_products(
    catalog_connection: sqlite3.Connection,
) -> None:
    first = catalog.list_products(catalog_connection, limit=1, offset=0)
    second = catalog.list_products(catalog_connection, limit=1, offset=1)

    assert first.items[0].product_id != second.items[0].product_id


@pytest.mark.parametrize("limit", [0, -1, catalog.MAX_LIMIT + 1])
def test_an_invalid_limit_is_rejected(
    catalog_connection: sqlite3.Connection, limit: int
) -> None:
    with pytest.raises(catalog.InvalidFilterError) as error:
        catalog.list_products(catalog_connection, limit=limit)

    assert "limit" in str(error.value)


def test_a_negative_offset_is_rejected(catalog_connection: sqlite3.Connection) -> None:
    with pytest.raises(catalog.InvalidFilterError) as error:
        catalog.list_products(catalog_connection, offset=-1)

    assert "offset" in str(error.value)


@pytest.mark.parametrize(("min_price", "max_price"), [(-1, None), (None, -5)])
def test_a_negative_price_is_rejected(
    catalog_connection: sqlite3.Connection, min_price: float | None, max_price: float | None
) -> None:
    with pytest.raises(catalog.InvalidFilterError):
        catalog.list_products(catalog_connection, min_price=min_price, max_price=max_price)


def test_an_inverted_price_range_is_rejected(catalog_connection: sqlite3.Connection) -> None:
    with pytest.raises(catalog.InvalidFilterError) as error:
        catalog.list_products(catalog_connection, min_price=500, max_price=100)

    assert "mínimo" in str(error.value)


def test_the_listing_adds_up_the_stock_of_every_warehouse(
    catalog_connection: sqlite3.Connection,
) -> None:
    page = catalog.list_products(catalog_connection, search="Nova Vision")

    # 7 en WH-A y 3 en WH-B.
    assert page.items[0].available_qty == 10


def test_a_product_without_stock_reports_zero(catalog_connection: sqlite3.Connection) -> None:
    page = catalog.list_products(catalog_connection, search="Flux Vision")

    assert page.items[0].available_qty == 0


def test_a_product_without_inventory_rows_reports_zero(
    catalog_connection: sqlite3.Connection,
) -> None:
    detail = catalog.get_product(catalog_connection, "MN-HDP-0003")

    assert detail.available_qty == 0


def test_a_product_without_a_price_reports_it_as_null(
    catalog_connection: sqlite3.Connection,
) -> None:
    detail = catalog.get_product(catalog_connection, "MN-HDP-0003")

    # Sin dato en la base, el precio viaja en null: no se estima.
    assert detail.current_price is None
    assert detail.currency is None
    assert detail.list_price is None


def test_brings_the_product_with_its_price_and_its_total_stock(
    catalog_connection: sqlite3.Connection,
) -> None:
    detail = catalog.get_product(catalog_connection, "MN-MON-0001")

    assert detail.name == "Nova Vision 24"
    assert detail.current_price == 468.62
    assert detail.list_price == 493.28
    assert detail.discount_percent == 5
    assert detail.available_qty == 10


def test_brings_the_specifications_of_the_product(
    catalog_connection: sqlite3.Connection,
) -> None:
    detail = catalog.get_product(catalog_connection, "MN-MON-0001")

    assert [specification.attribute_name for specification in detail.specifications] == [
        "Panel",
        "Screen Size",
    ]


def test_keeps_the_specification_whose_value_is_the_literal_none(
    catalog_connection: sqlite3.Connection,
) -> None:
    detail = catalog.get_product(catalog_connection, "MN-HDP-0001")

    water_resistance = [
        specification
        for specification in detail.specifications
        if specification.attribute_name == "Water Resistance"
    ]
    # No se filtra ni se convierte en null: el producto no es resistente al agua.
    assert water_resistance[0].value_text == "None"


def test_a_product_without_specifications_returns_an_empty_list(
    catalog_connection: sqlite3.Connection,
) -> None:
    detail = catalog.get_product(catalog_connection, "MN-HDP-0003")

    assert detail.specifications == []


def test_asking_for_a_product_that_does_not_exist_fails(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(catalog.ProductNotFoundError) as error:
        catalog.get_product(catalog_connection, "MN-NO-EXISTE")

    assert "MN-NO-EXISTE" in str(error.value)


def test_a_discontinued_product_can_still_be_consulted_by_its_id(
    catalog_connection: sqlite3.Connection,
) -> None:
    detail = catalog.get_product(catalog_connection, "MN-HDP-0002")

    assert detail.active is False


def test_lists_the_categories_with_their_subcategories(
    catalog_connection: sqlite3.Connection,
) -> None:
    categories = catalog.list_categories(catalog_connection)

    assert [category.subcategory_name for category in categories] == [
        "Gaming",
        "Gaming",
        "Office",
    ]
    assert categories[0].category_name == "Headphones"


def test_lists_the_brands_ordered_by_name(catalog_connection: sqlite3.Connection) -> None:
    brands = catalog.list_brands(catalog_connection)

    assert [brand.brand_name for brand in brands] == ["Flux", "NovaTech"]
    assert brands[0].positioning == "premium"
