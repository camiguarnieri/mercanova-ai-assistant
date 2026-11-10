"""Acceso a SQLite: resolución de la ruta, conexión y creación del esquema.

El esquema en sí vive en `schema.sql`, al lado de este módulo.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

__all__ = [
    "DatabaseError",
    "DatabaseConfigurationError",
    "DatabaseSchemaError",
    "DEFAULT_DATABASE_PATH",
    "TABLES",
    "database_path",
    "connect",
    "connection_scope",
    "create_schema",
    "table_counts",
]


class DatabaseError(RuntimeError):
    """Error de la capa de base de datos."""


class DatabaseConfigurationError(DatabaseError):
    """La ruta de la base de datos no se puede usar."""


class DatabaseSchemaError(DatabaseError):
    """El esquema no se pudo leer o aplicar."""


# Default seguro: dentro del repo, al lado del Excel del dataset.
DEFAULT_DATABASE_PATH = Path("data") / "mercanova.db"

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"

MEMORY_PATH = ":memory:"

# Las tablas que vienen del Excel de la cátedra, en orden de inserción: primero
# las referenciadas, después las que dependen. `orders` y `order_items` no están
# acá a propósito: son datos operativos que genera la aplicación, y la carga del
# dataset vacía y vuelve a escribir todo lo que esta tupla nombra.
TABLES: tuple[str, ...] = (
    "brands",
    "categories",
    "warehouses",
    "products",
    "specifications",
    "pricing",
    "inventory",
    "relations",
)


# Devuelve la ruta de la base, tomada de DATABASE_PATH o el default del proyecto.
def database_path() -> Path:
    """Resuelve la ruta del archivo SQLite a partir del entorno.

    Returns:
        La ruta de `DATABASE_PATH` si está definida y no vacía, si no
        `DEFAULT_DATABASE_PATH`.
    """
    configured = (os.getenv("DATABASE_PATH") or "").strip()
    return Path(configured) if configured else DEFAULT_DATABASE_PATH


# Abre una conexión a SQLite con claves foráneas activas y filas por nombre.
def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Abre una conexión a la base de datos.

    Args:
        path: Ruta del archivo SQLite, o `":memory:"` para una base en memoria.
            Si es `None` se usa `database_path()`.

    Returns:
        La conexión, con `row_factory` por nombre de columna y el pragma
        `foreign_keys` activado.

    Raises:
        DatabaseConfigurationError: Si la carpeta no se puede crear o el archivo
            no se puede abrir.
    """
    target = database_path() if path is None else path

    if str(target) != MEMORY_PATH:
        target = Path(target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise DatabaseConfigurationError(
                f"No se pudo crear la carpeta '{target.parent}' para la base de datos. "
                f"Revisá los permisos o apuntá DATABASE_PATH a otra ruta. Detalle: {error}"
            ) from error

    try:
        connection = sqlite3.connect(str(target))
    except sqlite3.Error as error:
        raise DatabaseConfigurationError(
            f"No se pudo abrir la base de datos en '{target}'. "
            f"Verificá que la ruta de DATABASE_PATH sea válida. Detalle: {error}"
        ) from error

    connection.row_factory = sqlite3.Row
    # El pragma es por conexión: sin esto SQLite ignora las claves foráneas.
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# Abre una conexión y la cierra al salir del bloque.
@contextmanager
def connection_scope(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Da una conexión con ciclo de vida acotado a un bloque `with`.

    Una conexión de SQLite solo se puede usar en el hilo que la creó, así que
    hay que abrirla dentro de la misma función que la consulta. Este context
    manager existe para que quien la usa no se olvide de cerrarla.

    Args:
        path: Ruta del archivo SQLite. Si es `None` se usa `database_path()`.

    Yields:
        La conexión, que se cierra al terminar el bloque, incluso si falla.
    """
    connection = connect(path)
    try:
        yield connection
    finally:
        connection.close()


# Aplica schema.sql sobre la conexión; se puede correr muchas veces sin efecto.
def create_schema(connection: sqlite3.Connection) -> None:
    """Crea las tablas y los índices si todavía no existen.

    Args:
        connection: Conexión abierta con `connect()`.

    Raises:
        DatabaseSchemaError: Si `schema.sql` falta o el DDL falla.
    """
    try:
        ddl = SCHEMA_FILE.read_text(encoding="utf-8")
    except OSError as error:
        raise DatabaseSchemaError(
            f"No se pudo leer el esquema en '{SCHEMA_FILE}'. "
            f"El archivo tiene que estar junto a backend/db.py. Detalle: {error}"
        ) from error

    try:
        connection.executescript(ddl)
    except sqlite3.Error as error:
        raise DatabaseSchemaError(
            f"Falló la creación del esquema definido en '{SCHEMA_FILE}'. Detalle: {error}"
        ) from error


# Cuenta las filas de cada tabla del esquema, para verificar una carga.
def table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Devuelve la cantidad de filas de cada tabla.

    Args:
        connection: Conexión abierta con `connect()`.

    Returns:
        Un diccionario `{nombre_de_tabla: filas}`, en el orden de `TABLES`.

    Raises:
        DatabaseSchemaError: Si alguna tabla del esquema no existe.
    """
    counts: dict[str, int] = {}
    for table in TABLES:
        try:
            row = connection.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
        except sqlite3.Error as error:
            raise DatabaseSchemaError(
                f"No se pudo contar las filas de la tabla '{table}'. "
                f"Creá el esquema con create_schema() antes de consultar. Detalle: {error}"
            ) from error
        counts[table] = int(row["total"])
    return counts
