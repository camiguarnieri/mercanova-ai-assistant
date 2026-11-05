"""Tests de scripts/dataset_reader.py: validación de hojas y conversión de tipos."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from conftest import write_workbook

from scripts import dataset_reader

# Columnas de la hoja Brands, en el orden del esquema.
BRAND_COLUMNS = ["brand_id", "brand_name", "country_of_origin", "positioning"]


def test_open_workbook_fails_with_an_actionable_message_when_the_file_does_not_exist(
    tmp_path: Path,
) -> None:
    with pytest.raises(dataset_reader.DatasetFileError) as error:
        dataset_reader.open_workbook(tmp_path / "no_existe.xlsx")

    assert "--excel" in str(error.value)


def test_open_workbook_fails_when_the_file_is_not_a_valid_excel(tmp_path: Path) -> None:
    fake = tmp_path / "roto.xlsx"
    fake.write_text("esto no es un xlsx", encoding="utf-8")

    with pytest.raises(dataset_reader.DatasetFileError) as error:
        dataset_reader.open_workbook(fake)

    assert ".xlsx" in str(error.value)


def test_sheet_rows_returns_the_values_in_the_order_of_the_schema(excel_path: Path) -> None:
    workbook = dataset_reader.open_workbook(excel_path)
    try:
        rows = dataset_reader.sheet_rows(workbook, "brands", BRAND_COLUMNS)
    finally:
        workbook.close()

    assert rows[0] == ("BR001", "NovaTech", "Uruguay", "balanced")


def test_sheet_rows_fails_when_the_sheet_is_missing(
    frames: dict[str, pd.DataFrame], tmp_path: Path
) -> None:
    del frames["Brands"]
    workbook = dataset_reader.open_workbook(write_workbook(frames, tmp_path / "sin_hoja.xlsx"))

    try:
        with pytest.raises(dataset_reader.DatasetSheetError) as error:
            dataset_reader.sheet_rows(workbook, "brands", BRAND_COLUMNS)
    finally:
        workbook.close()

    assert "Brands" in str(error.value)


def test_sheet_rows_fails_when_a_column_the_schema_needs_is_missing(
    frames: dict[str, pd.DataFrame], tmp_path: Path
) -> None:
    frames["Brands"] = frames["Brands"].drop(columns=["brand_name"])
    workbook = dataset_reader.open_workbook(
        write_workbook(frames, tmp_path / "sin_columna.xlsx")
    )

    try:
        with pytest.raises(dataset_reader.DatasetSheetError) as error:
            dataset_reader.sheet_rows(workbook, "brands", BRAND_COLUMNS)
    finally:
        workbook.close()

    assert "brand_name" in str(error.value)


def test_sheet_rows_warns_about_a_column_that_is_not_in_the_schema(
    frames: dict[str, pd.DataFrame], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    frames["Brands"]["columna_nueva"] = "sin usar"
    workbook = dataset_reader.open_workbook(
        write_workbook(frames, tmp_path / "columna_extra.xlsx")
    )

    try:
        rows = dataset_reader.sheet_rows(workbook, "brands", BRAND_COLUMNS)
    finally:
        workbook.close()

    assert "columna_nueva" in capsys.readouterr().out
    assert len(rows[0]) == len(BRAND_COLUMNS)


@pytest.mark.parametrize("value", ["None", "NA", "N/A", "NULL", "nan", "-"])
def test_normalize_column_keeps_the_texts_that_pandas_reads_as_null(value: str) -> None:
    """Esos textos son valores del catálogo, no celdas vacías."""
    assert dataset_reader.normalize_column(pd.Series([value]), "value_text") == [value]


def test_sheet_rows_keeps_the_literal_none_of_a_specification(excel_path: Path) -> None:
    columns = [
        "product_id",
        "attribute_group",
        "attribute_name",
        "value_text",
        "value_number",
        "unit",
    ]
    workbook = dataset_reader.open_workbook(excel_path)
    try:
        rows = dataset_reader.sheet_rows(workbook, "specifications", columns)
    finally:
        workbook.close()

    water_resistance = [row for row in rows if row[2] == "Water Resistance"]
    assert water_resistance[0][3] == "None"


@pytest.mark.parametrize("value", [None, float("nan"), "", "   ", pd.NaT])
def test_is_missing_detects_the_empty_cells(value: object) -> None:
    assert dataset_reader.is_missing(value) is True


@pytest.mark.parametrize("value", ["None", "NA", "IPX5", 0, 0.0, False])
def test_is_missing_does_not_discard_a_real_value(value: object) -> None:
    assert dataset_reader.is_missing(value) is False


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("launch_date", pd.Timestamp("2026-03-05"), "2026-03-05"),
        ("price_updated_at", pd.Timestamp("2026-10-17"), "2026-10-17"),
        ("inventory_updated_at", pd.Timestamp("2026-10-27 13:00"), "2026-10-27 13:00:00"),
        ("active", True, 1),
        ("tax_included", False, 0),
        ("pickup_enabled", True, 1),
        ("name", "  Nova  ", "Nova"),
        ("name", "   ", None),
        ("value_number", 24.0, 24.0),
        ("warranty_months", 12, 12),
    ],
)
def test_normalize_column_adapts_each_kind_of_value(
    column: str, value: object, expected: object
) -> None:
    assert dataset_reader.normalize_column(pd.Series([value]), column) == [expected]


@pytest.mark.parametrize(
    "column", ["launch_date", "inventory_updated_at", "active", "name", "value_number"]
)
def test_normalize_column_turns_missing_values_into_null(column: str) -> None:
    assert dataset_reader.normalize_column(pd.Series([None], dtype="object"), column) == [None]


def test_normalize_column_returns_native_python_types(excel_path: Path) -> None:
    workbook = dataset_reader.open_workbook(excel_path)
    try:
        frame = workbook.parse("Products")
    finally:
        workbook.close()

    weights = dataset_reader.normalize_column(frame["weight_kg"], "weight_kg")
    warranties = dataset_reader.normalize_column(frame["warranty_months"], "warranty_months")

    assert type(weights[0]) is float
    assert type(warranties[0]) is int
