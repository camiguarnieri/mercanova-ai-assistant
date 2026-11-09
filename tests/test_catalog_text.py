"""Tests de backend/catalog_text.py: los valores del catálogo escritos como texto.

Lo que se verifica es que el resultado de una herramienta diga lo mismo que
imprime la pantalla, sin dejar un número suelto ni un hueco que el modelo pueda
completar por su cuenta.
"""

from __future__ import annotations

import pytest

from backend import catalog_text
from backend.models import Specification


@pytest.mark.parametrize(
    ("value", "written"),
    [
        (0.0, "0"),
        (40.0, "40"),
        (5.3, "5.3"),
        (26.0, "26"),
        (182.94, "182.94"),
    ],
)
def test_a_number_is_written_without_the_decimal_zero(value: float, written: str) -> None:
    # Es el mismo formato que imprime la tabla: 40.0 se lee "40", no "40.0".
    assert catalog_text.number_text(value) == written


def test_a_zero_is_written_with_its_unit() -> None:
    # El caso que falló tres rondas: el 0 viajaba suelto y el modelo lo leía
    # como que el producto no tenía el dato.
    assert catalog_text.specification_text(None, 0.0, "h") == "0 h"


def test_a_number_is_written_with_its_unit() -> None:
    assert catalog_text.specification_text(None, 40.0, "h") == "40 h"


def test_a_number_without_unit_is_written_alone() -> None:
    assert catalog_text.specification_text(None, 5.3, None) == "5.3"


def test_a_text_value_travels_as_it_is() -> None:
    assert catalog_text.specification_text("IPS", None, None) == "IPS"


def test_the_none_text_is_written_as_the_screen_shows_it() -> None:
    # "None" es un valor real del catálogo: el producto NO tiene esa
    # característica. La pantalla imprime "No" y acá viaja igual.
    assert catalog_text.specification_text("None", None, None) == catalog_text.NO_FEATURE


def test_a_specification_without_any_value_says_the_catalog_does_not_have_it() -> None:
    assert (
        catalog_text.specification_text(None, None, "h")
        == catalog_text.MISSING_SPECIFICATION
    )


def test_a_missing_specification_is_not_written_as_a_zero() -> None:
    # Las dos cosas se escriben distinto a propósito: sin dato no es 0.
    assert catalog_text.specification_text(None, None, None) != "0"


def test_the_specifications_of_a_sheet_travel_as_text() -> None:
    specifications = [
        Specification(
            attribute_group="Battery", attribute_name="Battery Life", value_number=0.0, unit="h"
        ),
        Specification(attribute_group="Display", attribute_name="Panel", value_text="IPS"),
    ]

    assert catalog_text.specifications_text(specifications) == [
        {"attribute_group": "Battery", "attribute_name": "Battery Life", "value": "0 h"},
        {"attribute_group": "Display", "attribute_name": "Panel", "value": "IPS"},
    ]


def test_the_written_specification_does_not_carry_the_raw_number() -> None:
    # Si el número viaja al lado del texto, sigue estando el número que el
    # modelo puede volver a leer como ausencia.
    specification = Specification(
        attribute_group="Battery", attribute_name="Battery Life", value_number=0.0, unit="h"
    )

    written = catalog_text.specifications_text([specification])[0]

    assert set(written) == {"attribute_group", "attribute_name", "value"}


def test_having_stock_is_written_as_the_card_shows_it() -> None:
    assert catalog_text.stock_text(True) == "Con stock"


def test_not_having_stock_is_written_as_the_card_shows_it() -> None:
    assert catalog_text.stock_text(False) == "Sin stock"


@pytest.mark.parametrize("in_stock", [True, False])
def test_the_stock_text_never_carries_a_quantity(in_stock: bool) -> None:
    # Con el booleano, el modelo escribió "1 unidad disponible" para un producto
    # con 29. Si el texto trae un número, hay algo que puede repetir.
    assert not any(character.isdigit() for character in catalog_text.stock_text(in_stock))


def test_the_use_cases_travel_as_they_are_in_the_catalog() -> None:
    assert catalog_text.uses_text("office work; programming") == "office work; programming"


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_an_empty_use_case_field_says_the_catalog_does_not_clarify(empty: str | None) -> None:
    # Es el campo que el modelo completaba con el valor de otro producto.
    assert catalog_text.uses_text(empty) == catalog_text.MISSING_USES


def test_an_empty_use_case_field_never_travels_as_null() -> None:
    assert catalog_text.uses_text(None) is not None


def test_the_use_case_fields_of_a_product_are_written() -> None:
    product = {"product_id": "MN-MON-0001", "recommended_for": None, "not_recommended_for": None}

    written = catalog_text.with_uses_text(product)

    assert written["recommended_for"] == catalog_text.MISSING_USES
    assert written["not_recommended_for"] == catalog_text.MISSING_USES


def test_writing_the_use_case_fields_does_not_add_the_ones_that_are_not_there() -> None:
    # `Product` no tiene not_recommended_for: agregarlo sería inventar un campo.
    written = catalog_text.with_uses_text({"product_id": "MN-MON-0001"})

    assert written == {"product_id": "MN-MON-0001"}


def test_writing_the_use_case_fields_does_not_touch_the_product_it_received() -> None:
    product = {"recommended_for": None}

    catalog_text.with_uses_text(product)

    assert product["recommended_for"] is None
