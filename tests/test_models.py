"""Tests de backend/models.py: validación de los modelos de respuesta."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from backend.models import (
    Brand,
    Category,
    Product,
    ProductDetail,
    ProductPage,
    ProductSummary,
    ProductSummaryPage,
    Specification,
)

# Campos mínimos de un producto válido.
PRODUCT_FIELDS = {
    "product_id": "MN-MON-0001",
    "sku": "MON-10000",
    "name": "Nova Vision 24",
    "brand": "NovaTech",
    "category": "Monitors",
    "subcategory": "Office",
    "available_qty": 10,
    "active": True,
}

# Campos mínimos del resumen que lee el modelo. El stock es booleano: la
# cantidad solo sale de check_availability.
SUMMARY_FIELDS = {
    "product_id": "MN-MON-0001",
    "name": "Nova Vision 24",
    "brand": "NovaTech",
    "category": "Monitors",
    "in_stock": True,
}


def test_a_product_accepts_the_minimum_fields() -> None:
    product = Product.model_validate(PRODUCT_FIELDS)

    assert product.product_id == "MN-MON-0001"
    assert product.current_price is None


@pytest.mark.parametrize("field", ["product_id", "sku", "name", "available_qty", "active"])
def test_a_product_without_a_required_field_is_rejected(field: str) -> None:
    fields = {key: value for key, value in PRODUCT_FIELDS.items() if key != field}

    with pytest.raises(ValidationError):
        Product.model_validate(fields)


@pytest.mark.parametrize(
    "model, fields",
    [
        (Product, PRODUCT_FIELDS),
        (ProductSummary, SUMMARY_FIELDS),
        (Brand, {"brand_id": "BR001", "brand_name": "NovaTech"}),
        (Specification, {"attribute_group": "Display", "attribute_name": "Panel"}),
    ],
)
def test_an_extra_field_is_rejected(model: type, fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**fields, "campo_inventado": "x"})


def test_a_product_strips_the_extra_spaces_of_the_text() -> None:
    product = Product.model_validate({**PRODUCT_FIELDS, "name": "  Nova Vision 24  "})

    assert product.name == "Nova Vision 24"


@pytest.mark.parametrize("available_qty", ["diez", None])
def test_a_product_with_an_invalid_stock_is_rejected(available_qty: object) -> None:
    with pytest.raises(ValidationError):
        Product.model_validate({**PRODUCT_FIELDS, "available_qty": available_qty})


@pytest.mark.parametrize(("stored", "expected"), [(1, True), (0, False)])
def test_a_product_reads_the_active_flag_stored_as_an_integer(
    stored: int, expected: bool
) -> None:
    product = Product.model_validate({**PRODUCT_FIELDS, "active": stored})

    assert product.active is expected


def test_a_specification_keeps_the_literal_none_as_a_value() -> None:
    specification = Specification.model_validate(
        {
            "attribute_group": "Durability",
            "attribute_name": "Water Resistance",
            "value_text": "None",
        }
    )

    # "None" significa que el producto no tiene la característica.
    assert specification.value_text == "None"
    assert specification.value_number is None


def test_a_specification_can_carry_a_numeric_value_with_its_unit() -> None:
    specification = Specification.model_validate(
        {
            "attribute_group": "Display",
            "attribute_name": "Screen Size",
            "value_number": 24.0,
            "unit": "in",
        }
    )

    assert specification.value_number == 24.0
    assert specification.value_text is None


def test_a_product_detail_parses_the_dates_stored_as_text() -> None:
    detail = ProductDetail.model_validate(
        {**PRODUCT_FIELDS, "launch_date": "2026-03-05", "price_updated_at": "2026-10-17"}
    )

    assert detail.launch_date == date(2026, 3, 5)
    assert detail.price_updated_at == date(2026, 10, 17)


def test_a_product_detail_starts_without_specifications() -> None:
    detail = ProductDetail.model_validate(PRODUCT_FIELDS)

    assert detail.specifications == []


def test_a_product_detail_accepts_its_specifications() -> None:
    detail = ProductDetail.model_validate(
        {
            **PRODUCT_FIELDS,
            "specifications": [
                {"attribute_group": "Display", "attribute_name": "Panel", "value_text": "IPS"}
            ],
        }
    )

    assert detail.specifications[0].value_text == "IPS"


@pytest.mark.parametrize("field", ["category_id", "category_name", "subcategory_id"])
def test_a_category_without_a_required_field_is_rejected(field: str) -> None:
    fields = {
        "category_id": "CAT01",
        "category_name": "Monitors",
        "subcategory_id": "SUB001",
        "subcategory_name": "Office",
    }
    del fields[field]

    with pytest.raises(ValidationError):
        Category.model_validate(fields)


def test_a_summary_accepts_the_minimum_fields() -> None:
    summary = ProductSummary.model_validate(SUMMARY_FIELDS)

    assert summary.product_id == "MN-MON-0001"
    assert summary.current_price is None
    assert summary.not_recommended_for is None


@pytest.mark.parametrize("field", ["product_id", "name", "brand", "category", "in_stock"])
def test_a_summary_without_a_required_field_is_rejected(field: str) -> None:
    fields = {key: value for key, value in SUMMARY_FIELDS.items() if key != field}

    with pytest.raises(ValidationError):
        ProductSummary.model_validate(fields)


def test_a_summary_reports_the_stock_as_a_boolean() -> None:
    # Garantía del RF-07: con el número, el modelo lo repetía turnos después
    # como si lo hubiera vuelto a consultar.
    summary = ProductSummary.model_validate({**SUMMARY_FIELDS, "in_stock": 0})

    assert summary.in_stock is False


@pytest.mark.parametrize(
    "field", ["available_qty", "sku", "image_url", "tags", "subcategory", "short_description"]
)
def test_a_summary_does_not_accept_what_the_model_does_not_need(field: str) -> None:
    # Si una columna se cuela en la consulta, el modelo la rechaza en vez de
    # mandársela al LLM sin que nadie lo note.
    with pytest.raises(ValidationError):
        ProductSummary.model_validate({**SUMMARY_FIELDS, field: "x"})


def test_a_summary_carries_what_the_product_is_not_recommended_for() -> None:
    summary = ProductSummary.model_validate({**SUMMARY_FIELDS, "not_recommended_for": "gaming"})

    assert summary.not_recommended_for == "gaming"


def test_a_summary_page_reports_the_total_without_trimming() -> None:
    page = ProductSummaryPage.model_validate({"items": [SUMMARY_FIELDS], "total": 12})

    assert page.total == 12
    assert page.items[0].product_id == "MN-MON-0001"


def test_a_page_reports_that_there_are_more_results() -> None:
    page = ProductPage.model_validate(
        {
            "items": [PRODUCT_FIELDS],
            "total": 10,
            "limit": 1,
            "offset": 0,
            "has_more": True,
        }
    )

    assert page.has_more is True
    assert page.items[0].product_id == "MN-MON-0001"
