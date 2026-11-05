"""Tests de scripts/load_dataset.py: carga, repetibilidad, tipos y errores."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest
from conftest import write_workbook

from backend import db
from scripts import load_dataset
from scripts.dataset_reader import DatasetFileError, DatasetSheetError

# Filas que tiene que dejar el dataset de prueba en cada tabla.
EXPECTED_COUNTS = {
    "brands": 2,
    "categories": 2,
    "warehouses": 2,
    "products": 2,
    "specifications": 3,
    "pricing": 2,
    "inventory": 4,
    "relations": 1,
}


# Devuelve todo el contenido de la base, para comparar dos cargas.
def dump_database(database: Path) -> dict[str, list[tuple[object, ...]]]:
    """Lee todas las tablas de la base y las devuelve ordenadas.

    Args:
        database: Ruta del archivo SQLite.

    Returns:
        Un diccionario `{tabla: filas}`, con las filas como tuplas ordenadas.
    """
    connection = db.connect(database)
    try:
        return {
            table: sorted(
                tuple(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()
            )
            for table in db.TABLES
        }
    finally:
        connection.close()


def test_loads_every_sheet_of_the_dataset(excel_path: Path, database_file: Path) -> None:
    counts = load_dataset.load_dataset(excel_path, database_file)

    assert counts == EXPECTED_COUNTS


def test_running_the_load_twice_leaves_the_same_content(
    excel_path: Path, database_file: Path
) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    first = dump_database(database_file)

    load_dataset.load_dataset(excel_path, database_file)

    assert dump_database(database_file) == first


def test_running_the_load_twice_does_not_duplicate_rows(
    excel_path: Path, database_file: Path
) -> None:
    load_dataset.load_dataset(excel_path, database_file)

    assert load_dataset.load_dataset(excel_path, database_file) == EXPECTED_COUNTS


def test_does_not_modify_the_excel_file(excel_path: Path, database_file: Path) -> None:
    before = hashlib.sha256(excel_path.read_bytes()).hexdigest()

    load_dataset.load_dataset(excel_path, database_file)

    assert hashlib.sha256(excel_path.read_bytes()).hexdigest() == before


def test_uses_the_configured_database_when_none_is_given(
    excel_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "desde_el_entorno.db"
    monkeypatch.setenv("DATABASE_PATH", str(target))

    load_dataset.load_dataset(excel_path)

    assert target.is_file()


def test_stores_dates_as_iso_text(excel_path: Path, database_file: Path) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        row = connection.execute(
            "SELECT launch_date FROM products WHERE product_id = 'MN-MON-0001'"
        ).fetchone()
    finally:
        connection.close()

    assert row["launch_date"] == "2026-03-05"


def test_stores_timestamps_with_their_time(excel_path: Path, database_file: Path) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        row = connection.execute("SELECT inventory_updated_at FROM inventory").fetchone()
    finally:
        connection.close()

    assert row["inventory_updated_at"] == "2026-10-27 13:00:00"


def test_stores_booleans_as_zero_and_one(excel_path: Path, database_file: Path) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        rows = connection.execute(
            "SELECT product_id, active FROM products ORDER BY product_id"
        ).fetchall()
    finally:
        connection.close()

    assert [row["active"] for row in rows] == [1, 0]


def test_strips_the_extra_spaces_of_the_text(excel_path: Path, database_file: Path) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        row = connection.execute(
            "SELECT name FROM products WHERE product_id = 'MN-MON-0001'"
        ).fetchone()
    finally:
        connection.close()

    assert row["name"] == "Nova Vision 24"


def test_stores_the_empty_cells_as_null(excel_path: Path, database_file: Path) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        row = connection.execute(
            "SELECT not_recommended_for FROM products WHERE product_id = 'MN-MON-0001'"
        ).fetchone()
    finally:
        connection.close()

    assert row["not_recommended_for"] is None


def test_stores_the_literal_none_of_a_specification_as_text(
    excel_path: Path, database_file: Path
) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        row = connection.execute(
            "SELECT value_text FROM specifications WHERE attribute_name = 'Water Resistance'"
        ).fetchone()
    finally:
        connection.close()

    # "None" significa que el producto no es resistente al agua; NULL
    # significaría que no tenemos el dato, y no es lo mismo.
    assert row["value_text"] == "None"


def test_every_specification_has_exactly_one_value_column_filled(
    excel_path: Path, database_file: Path
) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        rows = connection.execute(
            "SELECT value_text, value_number FROM specifications"
        ).fetchall()
    finally:
        connection.close()

    assert all((row["value_text"] is None) != (row["value_number"] is None) for row in rows)


def test_keeps_the_numbers_as_numbers(excel_path: Path, database_file: Path) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        row = connection.execute(
            "SELECT weight_kg, warranty_months FROM products WHERE product_id = 'MN-MON-0001'"
        ).fetchone()
    finally:
        connection.close()

    assert isinstance(row["weight_kg"], float)
    assert isinstance(row["warranty_months"], int)


def test_the_loaded_data_has_no_foreign_key_violations(
    excel_path: Path, database_file: Path
) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    connection = db.connect(database_file)
    try:
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    assert violations == []


def test_fails_without_creating_the_database_when_the_excel_does_not_exist(
    tmp_path: Path, database_file: Path
) -> None:
    with pytest.raises(DatasetFileError):
        load_dataset.load_dataset(tmp_path / "no_existe.xlsx", database_file)

    assert not database_file.exists()


def test_does_not_load_anything_when_a_sheet_is_missing(
    frames: dict[str, pd.DataFrame], tmp_path: Path, database_file: Path
) -> None:
    del frames["Relations"]
    excel = write_workbook(frames, tmp_path / "sin_hoja.xlsx")

    with pytest.raises(DatasetSheetError):
        load_dataset.load_dataset(excel, database_file)

    connection = db.connect(database_file)
    try:
        # El esquema se creó, pero no se insertó ninguna fila.
        assert db.table_counts(connection) == dict.fromkeys(db.TABLES, 0)
    finally:
        connection.close()


def test_ignores_a_sheet_column_that_is_not_in_the_schema(
    frames: dict[str, pd.DataFrame], tmp_path: Path, database_file: Path
) -> None:
    frames["Brands"]["columna_nueva"] = "sin usar"
    excel = write_workbook(frames, tmp_path / "columna_extra.xlsx")

    counts = load_dataset.load_dataset(excel, database_file)

    assert counts == EXPECTED_COUNTS


def test_rejects_data_that_breaks_a_foreign_key(
    frames: dict[str, pd.DataFrame], tmp_path: Path, database_file: Path
) -> None:
    frames["Inventory"].loc[0, "product_id"] = "MN-MON-9999"
    excel = write_workbook(frames, tmp_path / "fk_invalida.xlsx")

    with pytest.raises(load_dataset.DatasetInsertError) as error:
        load_dataset.load_dataset(excel, database_file)

    assert "inventory" in str(error.value)


def test_a_failed_load_leaves_the_previous_data_untouched(
    frames: dict[str, pd.DataFrame], excel_path: Path, tmp_path: Path, database_file: Path
) -> None:
    load_dataset.load_dataset(excel_path, database_file)
    frames["Pricing"].loc[0, "current_price"] = 10_000.0  # mayor que el precio de lista
    broken = write_workbook(frames, tmp_path / "precio_invalido.xlsx")

    with pytest.raises(load_dataset.DatasetInsertError):
        load_dataset.load_dataset(broken, database_file)

    connection = db.connect(database_file)
    try:
        counts = db.table_counts(connection)
    finally:
        connection.close()
    assert counts == EXPECTED_COUNTS


def test_table_columns_follows_the_order_of_the_schema(database_file: Path) -> None:
    connection = db.connect(database_file)
    try:
        db.create_schema(connection)
        columns = load_dataset.table_columns(connection, "brands")
    finally:
        connection.close()

    assert columns == ["brand_id", "brand_name", "country_of_origin", "positioning"]


def test_main_loads_the_dataset_and_prints_the_rows_of_each_table(
    excel_path: Path, database_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = load_dataset.main(["--excel", str(excel_path), "--database", str(database_file)])

    output = capsys.readouterr().out
    assert exit_code == 0
    for table, total in EXPECTED_COUNTS.items():
        assert f"{table}" in output
        assert str(total) in output


def test_main_reports_the_error_and_fails_when_the_excel_is_missing(
    tmp_path: Path, database_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = load_dataset.main(
        ["--excel", str(tmp_path / "no_existe.xlsx"), "--database", str(database_file)]
    )

    assert exit_code == 1
    assert "Error:" in capsys.readouterr().err
