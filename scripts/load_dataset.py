"""Carga el Excel del dataset en SQLite.

Script repetible: vacía las tablas y las vuelve a insertar en una sola
transacción, así que correrlo dos veces deja la base igual. La lectura del Excel
está en `dataset_reader.py`, que nunca escribe sobre el archivo original.

Uso:
    python scripts/load_dataset.py [--excel RUTA] [--database RUTA]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db, environment  # noqa: E402  (después de ajustar sys.path)
from scripts import dataset_reader  # noqa: E402
from scripts.dataset_reader import DatasetError  # noqa: E402

DEFAULT_EXCEL_PATH = Path("data") / "MercaNova_dataset.xlsx"


class DatasetInsertError(DatasetError):
    """Los datos del Excel no entran en el esquema."""


# Devuelve los nombres de columna de una tabla, en el orden del esquema.
def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    """Lee las columnas de una tabla desde el esquema SQLite.

    Args:
        connection: Conexión abierta con el esquema ya creado.
        table: Nombre de la tabla.

    Returns:
        Los nombres de las columnas en el orden declarado.
    """
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row["name"]) for row in rows]


# Vacía las tablas y vuelve a insertar las 8 hojas en una sola transacción.
def load_dataset(excel_path: Path, database: str | Path | None = None) -> dict[str, int]:
    """Carga las 8 hojas del Excel en SQLite.

    Args:
        excel_path: Ruta del Excel del dataset.
        database: Ruta de la base. Si es `None` se usa `DATABASE_PATH`.

    Returns:
        La cantidad de filas que quedó en cada tabla.

    Raises:
        DatasetFileError: Si el Excel no se puede leer.
        DatasetSheetError: Si falta una hoja o una columna.
        DatasetInsertError: Si los datos violan el esquema.
        DatabaseError: Si la base o el esquema no se pueden preparar.
    """
    workbook = dataset_reader.open_workbook(excel_path)
    connection = db.connect(database)
    try:
        db.create_schema(connection)
        columns_by_table = {table: table_columns(connection, table) for table in db.TABLES}
        # Se lee todo el Excel antes de tocar la base, para no empezar a
        # escribir si una hoja está mal.
        rows_by_table = {
            table: dataset_reader.sheet_rows(workbook, table, columns_by_table[table])
            for table in db.TABLES
        }

        table = ""
        try:
            with connection:  # una sola transacción: entra todo o no entra nada
                # Se borra en orden inverso para no romper las claves foráneas.
                for table in reversed(db.TABLES):
                    connection.execute(f"DELETE FROM {table}")
                for table in db.TABLES:
                    columns = columns_by_table[table]
                    placeholders = ", ".join("?" * len(columns))
                    statement = (
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
                    )
                    connection.executemany(statement, rows_by_table[table])
        except sqlite3.Error as error:
            raise DatasetInsertError(
                f"Falló la carga de la tabla '{table}'. La base quedó como estaba. "
                f"Revisá los datos de la hoja "
                f"'{dataset_reader.SHEET_BY_TABLE[table]}'. Detalle: {error}"
            ) from error

        return db.table_counts(connection)
    finally:
        connection.close()
        workbook.close()


# Punto de entrada: carga el dataset e imprime las filas de cada tabla.
def main(argv: list[str] | None = None) -> int:
    """Corre la carga desde la línea de comandos.

    Args:
        argv: Argumentos, sin el nombre del programa. `None` usa `sys.argv`.

    Returns:
        0 si la carga terminó bien, 1 si hubo un error esperado.
    """
    # El .env se carga acá y no al importar el módulo: este script también se
    # usa desde los tests, que importan `main` y no tienen por qué heredar el
    # .env de la máquina. Sin esto, --database default y DATABASE_PATH del
    # archivo no coincidirían con la base que usa el servidor.
    environment.load_env_file()

    parser = argparse.ArgumentParser(description="Carga el Excel de MercaNova en SQLite.")
    parser.add_argument(
        "--excel", type=Path, default=DEFAULT_EXCEL_PATH, help="Ruta del Excel del dataset."
    )
    parser.add_argument(
        "--database", type=Path, default=None, help="Ruta de la base (default: DATABASE_PATH)."
    )
    arguments = parser.parse_args(argv)

    target = arguments.database if arguments.database is not None else db.database_path()
    print(f"Cargando '{arguments.excel}' en '{target}'...")
    try:
        counts = load_dataset(arguments.excel, arguments.database)
    except (DatasetError, db.DatabaseError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    width = max(len(table) for table in counts)
    print("\nFilas por tabla:")
    for table, total in counts.items():
        print(f"  {table.ljust(width)}  {total:>5}")
    print(f"\nTotal: {sum(counts.values())} filas en {len(counts)} tablas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
