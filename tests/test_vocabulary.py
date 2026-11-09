"""Tests de backend/vocabulary.py: el esquema que sale de la base, no de una lista."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend import db, tool_schemas
from backend.vocabulary import Vocabulary


# Trae los parámetros de search_products del esquema armado.
def search_properties(schemas: list[dict]) -> dict:
    """Devuelve las propiedades del primer esquema, que es search_products."""
    return schemas[0]["function"]["parameters"]["properties"]


def test_the_schemas_come_out_with_the_six_tools(
    catalog_connection: sqlite3.Connection,
) -> None:
    schemas = Vocabulary().schemas(catalog_connection)

    assert [schema["function"]["name"] for schema in schemas] == list(tool_schemas.TOOL_NAMES)


def test_the_categories_come_from_the_database(
    catalog_connection: sqlite3.Connection,
) -> None:
    properties = search_properties(Vocabulary().schemas(catalog_connection))

    assert properties["category"]["enum"] == ["Headphones", "Monitors"]


def test_the_use_cases_come_from_the_database(
    catalog_connection: sqlite3.Connection,
) -> None:
    properties = search_properties(Vocabulary().schemas(catalog_connection))

    # Separados del punto y coma de recommended_for, sin repetir y ordenados.
    assert properties["recommended_for"]["enum"] == [
        "casual listening",
        "content creation",
        "gaming",
        "office work",
        "programming",
        "travel",
    ]


def test_the_categories_are_not_repeated_in_the_description(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Van solo en el enum: repetirlas en la descripción no le dice nada nuevo al
    # modelo y ocupa el doble en su ventana de contexto.
    properties = search_properties(Vocabulary().schemas(catalog_connection))

    description = properties["category"]["description"]
    for value in properties["category"]["enum"]:
        assert value not in description


def test_the_description_of_the_category_points_at_the_enum(
    catalog_connection: sqlite3.Connection,
) -> None:
    properties = search_properties(Vocabulary().schemas(catalog_connection))

    assert "enumera este parámetro" in properties["category"]["description"]


def test_the_use_cases_are_grouped_by_category_in_the_description(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Lo único que el enum no puede decir: con qué categoría va cada uno.
    description = search_properties(Vocabulary().schemas(catalog_connection))[
        "recommended_for"
    ]["description"]

    assert "Headphones: casual listening, office work, travel" in description
    assert "Monitors: content creation, gaming, office work, programming" in description


def test_the_description_asks_to_choose_within_the_category(
    catalog_connection: sqlite3.Connection,
) -> None:
    description = search_properties(Vocabulary().schemas(catalog_connection))[
        "recommended_for"
    ]["description"]

    assert "uno de los de la categoría que estás buscando" in description


def test_the_discontinued_products_do_not_bring_vocabulary(
    catalog_connection: sqlite3.Connection,
) -> None:
    # "Flux Buds" está dado de baja: su caso de uso no se puede recomendar.
    properties = search_properties(Vocabulary().schemas(catalog_connection))

    assert "in-ear" not in properties["recommended_for"]["enum"]


def test_the_schema_is_built_once_and_reused(
    catalog_connection: sqlite3.Connection,
) -> None:
    terms = Vocabulary()

    first = terms.schemas(catalog_connection)
    second = terms.schemas(catalog_connection)

    # El esquema viaja en cada pedido al modelo: se arma una sola vez.
    assert first is second


def test_the_schema_is_not_built_from_the_database_of_another_vocabulary(
    catalog_connection: sqlite3.Connection,
) -> None:
    other = Vocabulary()

    assert Vocabulary().schemas(catalog_connection) is not other.schemas(catalog_connection)


def test_a_database_without_schema_fails_instead_of_inventing_the_vocabulary(
    tmp_path: Path,
) -> None:
    connection = db.connect(tmp_path / "vacia.db")
    try:
        with pytest.raises(sqlite3.Error):
            Vocabulary().schemas(connection)
    finally:
        connection.close()


def test_a_failed_build_is_retried(tmp_path: Path, catalog_database: Path) -> None:
    terms = Vocabulary()
    empty = db.connect(tmp_path / "vacia.db")
    try:
        with pytest.raises(sqlite3.Error):
            terms.schemas(empty)
    finally:
        empty.close()

    # Si al arrancar la base no estaba cargada, el primer mensaje lo reintenta.
    with db.connection_scope(catalog_database) as connection:
        assert search_properties(terms.schemas(connection))["category"]["enum"]


def test_without_vocabulary_the_tools_still_work() -> None:
    # Si la base no se puede leer, el asistente sigue andando con menos ayuda.
    properties = search_properties(tool_schemas.build_tool_schemas())

    assert "enum" not in properties["category"]
    assert properties["category"]["description"]


def test_the_parameters_are_the_same_with_and_without_vocabulary(
    catalog_connection: sqlite3.Connection,
) -> None:
    # La validación de argumentos usa el esquema sin vocabulario: los nombres
    # de los parámetros tienen que ser los mismos.
    with_terms = search_properties(Vocabulary().schemas(catalog_connection))

    assert set(with_terms) == set(search_properties(tool_schemas.TOOL_SCHEMAS))
