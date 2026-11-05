"""Tests de backend/db.py: ruta configurable, conexión y esquema."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend import db

# Filas mínimas para poder insertar un producto válido.
BRAND_ROW = ("BR001", "NovaTech", "Uruguay", "balanced")
CATEGORY_ROW = ("SUB001", "CAT01", "Monitors", "Office", "Electronics", 1)
PRODUCT_ROW = (
    "MN-MON-0001",
    "MON-10000",
    "Nova Vision 24",
    "NovaTech",
    "BR001",
    "Monitors",
    "Office",
    None,
    None,
    None,
    None,
    None,
    None,
    "Black",
    6.5,
    50.0,
    32.0,
    20.0,
    12,
    30,
    4.3,
    100,
    "2026-03-05",
    1,
    None,
)


# Crea una base en memoria con el esquema aplicado.
@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    """Conexión en memoria con las tablas ya creadas."""
    conn = db.connect(db.MEMORY_PATH)
    db.create_schema(conn)
    yield conn
    conn.close()


# Inserta marca, categoría y producto base, para probar las claves foráneas.
def insert_base_rows(connection: sqlite3.Connection) -> None:
    """Carga una marca, una categoría y un producto consistentes."""
    connection.execute("INSERT INTO brands VALUES (?, ?, ?, ?)", BRAND_ROW)
    connection.execute("INSERT INTO categories VALUES (?, ?, ?, ?, ?, ?)", CATEGORY_ROW)
    placeholders = ", ".join("?" * len(PRODUCT_ROW))
    connection.execute(f"INSERT INTO products VALUES ({placeholders})", PRODUCT_ROW)


def test_database_path_uses_the_project_default_when_the_variable_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_PATH", raising=False)

    assert db.database_path() == db.DEFAULT_DATABASE_PATH


def test_database_path_reads_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", "otra/ruta/catalogo.db")

    assert db.database_path() == Path("otra/ruta/catalogo.db")


@pytest.mark.parametrize("configured", ["", "   "])
def test_database_path_ignores_an_empty_variable(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    monkeypatch.setenv("DATABASE_PATH", configured)

    assert db.database_path() == db.DEFAULT_DATABASE_PATH


def test_connect_uses_the_configured_path_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "desde_el_entorno.db"
    monkeypatch.setenv("DATABASE_PATH", str(target))

    connection = db.connect()
    try:
        db.create_schema(connection)
    finally:
        connection.close()

    assert target.is_file()


def test_connect_creates_the_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nueva" / "carpeta" / "catalogo.db"

    connection = db.connect(target)
    try:
        db.create_schema(connection)
    finally:
        connection.close()

    assert target.is_file()


def test_connect_fails_with_an_actionable_message_when_the_path_is_unusable(
    tmp_path: Path,
) -> None:
    # Un archivo no puede ser la carpeta que contenga a la base.
    blocking_file = tmp_path / "archivo"
    blocking_file.write_text("no soy una carpeta", encoding="utf-8")

    with pytest.raises(db.DatabaseConfigurationError) as error:
        db.connect(blocking_file / "catalogo.db")

    assert "DATABASE_PATH" in str(error.value)


def test_connect_returns_rows_accessible_by_column_name(connection: sqlite3.Connection) -> None:
    insert_base_rows(connection)

    row = connection.execute("SELECT product_id, name FROM products").fetchone()

    assert row["product_id"] == "MN-MON-0001"
    assert row["name"] == "Nova Vision 24"


def test_connect_enables_foreign_key_enforcement(connection: sqlite3.Connection) -> None:
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_create_schema_creates_every_table_of_the_dataset(
    connection: sqlite3.Connection,
) -> None:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()

    assert set(db.TABLES) <= {row["name"] for row in rows}


def test_create_schema_can_run_twice_without_failing(connection: sqlite3.Connection) -> None:
    db.create_schema(connection)

    assert db.table_counts(connection)["products"] == 0


def test_create_schema_reports_an_actionable_error_when_the_file_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(db, "SCHEMA_FILE", tmp_path / "no_existe.sql")
    connection = db.connect(db.MEMORY_PATH)

    try:
        with pytest.raises(db.DatabaseSchemaError) as error:
            db.create_schema(connection)
    finally:
        connection.close()

    assert "backend/db.py" in str(error.value)


def test_table_counts_returns_zero_for_every_table_of_a_new_schema(
    connection: sqlite3.Connection,
) -> None:
    assert db.table_counts(connection) == dict.fromkeys(db.TABLES, 0)


def test_table_counts_fails_when_the_schema_was_not_created() -> None:
    connection = db.connect(db.MEMORY_PATH)

    try:
        with pytest.raises(db.DatabaseSchemaError) as error:
            db.table_counts(connection)
    finally:
        connection.close()

    assert "create_schema" in str(error.value)


def test_a_product_cannot_reference_a_brand_that_does_not_exist(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("INSERT INTO categories VALUES (?, ?, ?, ?, ?, ?)", CATEGORY_ROW)
    row = list(PRODUCT_ROW)
    row[4] = "BR999"
    placeholders = ", ".join("?" * len(row))

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(f"INSERT INTO products VALUES ({placeholders})", row)


def test_a_product_cannot_reference_a_category_subcategory_pair_that_does_not_exist(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("INSERT INTO brands VALUES (?, ?, ?, ?)", BRAND_ROW)
    connection.execute("INSERT INTO categories VALUES (?, ?, ?, ?, ?, ?)", CATEGORY_ROW)
    row = list(PRODUCT_ROW)
    row[6] = "Gaming"  # "Monitors/Gaming" no está en categories
    placeholders = ", ".join("?" * len(row))

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(f"INSERT INTO products VALUES ({placeholders})", row)


def test_two_products_cannot_share_the_same_sku(connection: sqlite3.Connection) -> None:
    insert_base_rows(connection)
    row = list(PRODUCT_ROW)
    row[0] = "MN-MON-0002"  # otro producto, mismo sku
    placeholders = ", ".join("?" * len(row))

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(f"INSERT INTO products VALUES ({placeholders})", row)


def test_the_same_attribute_cannot_be_loaded_twice_for_a_product(
    connection: sqlite3.Connection,
) -> None:
    insert_base_rows(connection)
    specification = ("MN-MON-0001", "Display", "Panel", "IPS", None, None)
    connection.execute("INSERT INTO specifications VALUES (?, ?, ?, ?, ?, ?)", specification)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO specifications VALUES (?, ?, ?, ?, ?, ?)", specification)


def test_a_specification_cannot_have_both_value_columns_empty(
    connection: sqlite3.Connection,
) -> None:
    insert_base_rows(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO specifications VALUES (?, ?, ?, ?, ?, ?)",
            ("MN-MON-0001", "Durability", "Water Resistance", None, None, None),
        )


def test_a_specification_cannot_have_both_value_columns_filled(
    connection: sqlite3.Connection,
) -> None:
    insert_base_rows(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO specifications VALUES (?, ?, ?, ?, ?, ?)",
            ("MN-MON-0001", "Display", "Screen Size", '24"', 24.0, "in"),
        )


@pytest.mark.parametrize(
    ("value_text", "value_number"),
    [("IPX5", None), (None, 24.0), ("None", None)],
)
def test_a_specification_with_exactly_one_value_is_accepted(
    connection: sqlite3.Connection, value_text: str | None, value_number: float | None
) -> None:
    insert_base_rows(connection)

    connection.execute(
        "INSERT INTO specifications VALUES (?, ?, ?, ?, ?, ?)",
        ("MN-MON-0001", "Durability", "Water Resistance", value_text, value_number, None),
    )

    row = connection.execute("SELECT value_text, value_number FROM specifications").fetchone()
    assert (row["value_text"], row["value_number"]) == (value_text, value_number)


def test_the_current_price_cannot_be_higher_than_the_list_price(
    connection: sqlite3.Connection,
) -> None:
    insert_base_rows(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO pricing VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("MN-MON-0001", "USD", 100.0, 150.0, 0, 1, "2026-10-17"),
        )


def test_a_price_cannot_be_negative(connection: sqlite3.Connection) -> None:
    insert_base_rows(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO pricing VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("MN-MON-0001", "USD", -1.0, -1.0, 0, 1, "2026-10-17"),
        )


def test_the_available_quantity_has_to_match_the_stock_minus_the_reserved(
    connection: sqlite3.Connection,
) -> None:
    insert_base_rows(connection)
    connection.execute(
        "INSERT INTO warehouses VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("WH-A", "MercaNova Centro", "Montevideo", "Montevideo", "Uruguay", 1, 1),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("MN-MON-0001", "WH-A", 10, 3, 9, "In stock", "2026-10-27 13:00:00"),
        )


def test_inventory_cannot_reference_a_warehouse_that_does_not_exist(
    connection: sqlite3.Connection,
) -> None:
    insert_base_rows(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("MN-MON-0001", "WH-999", 10, 3, 7, "In stock", "2026-10-27 13:00:00"),
        )


def test_a_product_cannot_be_related_to_itself(connection: sqlite3.Connection) -> None:
    insert_base_rows(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO relations VALUES (?, ?, ?, ?)",
            ("MN-MON-0001", "MN-MON-0001", "alternative_to", 0.8),
        )


def test_an_unknown_relation_type_is_rejected(connection: sqlite3.Connection) -> None:
    insert_base_rows(connection)
    # El producto relacionado tiene que existir, para que el error que salte
    # sea el del tipo de relación y no el de la clave foránea.
    second_product = list(PRODUCT_ROW)
    second_product[0] = "MN-MON-0002"
    second_product[1] = "MON-10001"
    placeholders = ", ".join("?" * len(second_product))
    connection.execute(f"INSERT INTO products VALUES ({placeholders})", second_product)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO relations VALUES (?, ?, ?, ?)",
            ("MN-MON-0001", "MN-MON-0002", "parecido_a", 0.8),
        )
