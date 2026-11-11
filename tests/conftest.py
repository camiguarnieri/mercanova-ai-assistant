"""Fixtures compartidas: datos de prueba y un Excel mínimo, armado en el test.

Ningún test lee el Excel de la cátedra ni la base real: todo se genera acá.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import catalog_data  # noqa: E402  (módulo auxiliar de tests/)

from backend import environment  # noqa: E402  (después de ajustar sys.path)

# Antes de importar `backend.api`, que carga el `.env` al importarse: así el
# archivo de esta máquina no se lee en ningún test. Tiene que ser acá y no en
# una fixture porque los orígenes de CORS se resuelven cuando se arma el
# middleware, al importar el módulo, antes de que corra cualquier fixture.
environment.skip_env_file()

from backend import api, db  # noqa: E402  (después de neutralizar el .env)

# Las precargas reales, guardadas antes de reemplazarlas, para los tests que
# verifican el arranque.
PRELOAD_ASSISTANT = api.preload_assistant
PRELOAD_VOCABULARY = api.preload_vocabulary


@pytest.fixture(autouse=True)
def without_the_project_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Saca del entorno las variables del proyecto, en todos los tests.

    El `skip_env_file()` de arriba se ocupa del archivo; esto se ocupa de la
    otra fuente, que es lo que quien corre los tests tenga exportado en su
    terminal. Sin esta limpieza, un test que espera el default del código
    pasaría o fallaría según la máquina, que es justo lo que no puede pasar.

    Se limpia la lista de `environment.PROJECT_VARIABLES`, así una variable
    nueva queda cubierta sin que haya que acordarse de agregarla acá. Cada test
    que necesita un valor lo pone con `monkeypatch.setenv`, y `monkeypatch`
    devuelve el entorno a como estaba al terminar.

    Se vuelve a dejar en vacío lo anotado como venido del archivo, por si un
    test cargó uno propio: así una variable que otro test pone con `setenv` no
    se reporta como venida de un `.env`.
    """
    for variable in environment.PROJECT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(environment, "_from_file", frozenset())


@pytest.fixture(autouse=True)
def without_startup_preloads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita que el arranque de la API busque Ollama o la base real.

    Los tres pasos del arranque corren en el lifespan de FastAPI, y
    `TestClient` lo ejecuta al entrar al bloque `with`: uno llama a Ollama y
    los otros dos abren la base de `DATABASE_PATH`. Ningún test llama al
    modelo ni toca la base real, así que se reemplazan por nada. Los tests que
    verifican el arranque los vuelven a poner.
    """
    monkeypatch.setattr(api, "ensure_schema", lambda: None)
    monkeypatch.setattr(api, "preload_assistant", lambda: None)
    monkeypatch.setattr(api, "preload_vocabulary", lambda: None)


@pytest.fixture
def with_model_preload(
    without_startup_preloads: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vuelve a poner la precarga del modelo, para probar el arranque.

    Depende de la fixture que la reemplaza para correr después de ella. El test
    que la usa reemplaza `llm.preload_model`, así que tampoco llega a Ollama.
    """
    monkeypatch.setattr(api, "preload_assistant", PRELOAD_ASSISTANT)


@pytest.fixture
def with_vocabulary_preload(
    without_startup_preloads: None, monkeypatch: pytest.MonkeyPatch, catalog_database: Path
) -> None:
    """Vuelve a poner la precarga del vocabulario, apuntada a la base de prueba.

    `DATABASE_PATH` se cambia para que el arranque no lea la base real.
    """
    monkeypatch.setenv("DATABASE_PATH", str(catalog_database))
    monkeypatch.setattr(api, "preload_vocabulary", PRELOAD_VOCABULARY)


# Devuelve las 8 hojas de un dataset chico y consistente, listo para modificar.
def build_frames() -> dict[str, pd.DataFrame]:
    """Arma un dataset de prueba con las 8 hojas del Excel real.

    Returns:
        Un diccionario `{nombre_de_hoja: DataFrame}` que respeta todas las
        claves foráneas y los CHECK del esquema.
    """
    return {
        "Brands": pd.DataFrame(
            [
                {
                    "brand_id": "BR001",
                    "brand_name": "NovaTech",
                    "country_of_origin": "Uruguay",
                    "positioning": "balanced",
                },
                {
                    "brand_id": "BR002",
                    "brand_name": "Flux",
                    "country_of_origin": "Brasil",
                    "positioning": "premium",
                },
            ]
        ),
        "Categories": pd.DataFrame(
            [
                {
                    "subcategory_id": "SUB001",
                    "category_id": "CAT01",
                    "category_name": "Monitors",
                    "subcategory_name": "Office",
                    "department": "Electronics",
                    "sort_order": 1,
                },
                {
                    "subcategory_id": "SUB002",
                    "category_id": "CAT01",
                    "category_name": "Monitors",
                    "subcategory_name": "Gaming",
                    "department": "Electronics",
                    "sort_order": 2,
                },
            ]
        ),
        "Warehouses": pd.DataFrame(
            [
                {
                    "warehouse_id": "WH-A",
                    "warehouse_name": "MercaNova Centro",
                    "city": "Montevideo",
                    "department": "Montevideo",
                    "country": "Uruguay",
                    "pickup_enabled": True,
                    "shipping_enabled": True,
                },
                {
                    "warehouse_id": "WH-B",
                    "warehouse_name": "MercaNova Norte",
                    "city": "Salto",
                    "department": "Salto",
                    "country": "Uruguay",
                    "pickup_enabled": False,
                    "shipping_enabled": True,
                },
            ]
        ),
        "Products": pd.DataFrame(
            [
                {
                    "product_id": "MN-MON-0001",
                    "sku": "MON-10000",
                    # Con espacios de sobra a propósito: la carga los limpia.
                    "name": "  Nova Vision 24  ",
                    "brand": "NovaTech",
                    "brand_id": "BR001",
                    "category": "Monitors",
                    "subcategory": "Office",
                    "short_description": "Monitor de 24 pulgadas.",
                    "description": "Monitor IPS de 24 pulgadas para oficina.",
                    "recommended_for": "office work",
                    "not_recommended_for": None,
                    "key_features": "24-inch; IPS",
                    "tags": "monitor; office",
                    "color": "Black",
                    "weight_kg": 6.5,
                    "width_cm": 50.0,
                    "height_cm": 32.0,
                    "depth_cm": 20.0,
                    "warranty_months": 12,
                    "return_days": 30,
                    "rating": 4.3,
                    "review_count": 100,
                    "launch_date": pd.Timestamp("2026-03-05"),
                    "active": True,
                    "image_url": "https://placehold.co/800x600/png?text=MON-10000",
                },
                {
                    "product_id": "MN-MON-0002",
                    "sku": "MON-10001",
                    "name": "Flux Vision 27",
                    "brand": "Flux",
                    "brand_id": "BR002",
                    "category": "Monitors",
                    "subcategory": "Gaming",
                    "short_description": "Monitor gamer de 27 pulgadas.",
                    "description": "Monitor de 27 pulgadas y 240 Hz.",
                    "recommended_for": "gaming",
                    "not_recommended_for": "office work",
                    "key_features": "27-inch; 240 Hz",
                    "tags": "monitor; gaming",
                    "color": "White",
                    "weight_kg": 7.1,
                    "width_cm": 61.0,
                    "height_cm": 36.0,
                    "depth_cm": 22.0,
                    "warranty_months": 24,
                    "return_days": 30,
                    "rating": 4.7,
                    "review_count": 250,
                    "launch_date": pd.Timestamp("2026-05-20"),
                    "active": False,
                    "image_url": "https://placehold.co/800x600/png?text=MON-10001",
                },
            ]
        ),
        "Specifications": pd.DataFrame(
            [
                {
                    "product_id": "MN-MON-0001",
                    "attribute_group": "Display",
                    "attribute_name": "Screen Size",
                    "value_text": None,
                    "value_number": 24.0,
                    "unit": "in",
                },
                {
                    "product_id": "MN-MON-0001",
                    "attribute_group": "Display",
                    "attribute_name": "Panel",
                    "value_text": "IPS",
                    "value_number": None,
                    "unit": None,
                },
                {
                    # El texto literal "None" es un valor del catálogo: el
                    # producto no tiene la característica. pandas lo convierte
                    # a NaN si no se lo frena, y acá se verifica que no pase.
                    "product_id": "MN-MON-0002",
                    "attribute_group": "Durability",
                    "attribute_name": "Water Resistance",
                    "value_text": "None",
                    "value_number": None,
                    "unit": None,
                },
            ]
        ),
        "Pricing": pd.DataFrame(
            [
                {
                    "product_id": "MN-MON-0001",
                    "currency": "USD",
                    "list_price": 493.28,
                    "current_price": 468.62,
                    "discount_percent": 5,
                    "tax_included": True,
                    "price_updated_at": pd.Timestamp("2026-10-17"),
                },
                {
                    "product_id": "MN-MON-0002",
                    "currency": "USD",
                    "list_price": 700.00,
                    "current_price": 700.00,
                    "discount_percent": 0,
                    "tax_included": False,
                    "price_updated_at": pd.Timestamp("2026-10-18"),
                },
            ]
        ),
        "Inventory": pd.DataFrame(
            [
                {
                    "product_id": product,
                    "warehouse_id": warehouse,
                    "on_hand_qty": 10,
                    "reserved_qty": 3,
                    "available_qty": 7,
                    "inventory_status": "In stock",
                    "inventory_updated_at": pd.Timestamp("2026-10-27 13:00:00"),
                }
                for product in ("MN-MON-0001", "MN-MON-0002")
                for warehouse in ("WH-A", "WH-B")
            ]
        ),
        "Relations": pd.DataFrame(
            [
                {
                    "product_id": "MN-MON-0001",
                    "related_product_id": "MN-MON-0002",
                    "relation_type": "alternative_to",
                    "strength": 0.82,
                }
            ]
        ),
    }


# Escribe las hojas en un .xlsx y devuelve su ruta.
def write_workbook(frames: dict[str, pd.DataFrame], path: Path) -> Path:
    """Guarda las hojas de prueba en un archivo Excel.

    Args:
        frames: Hojas a escribir, `{nombre: DataFrame}`.
        path: Ruta del `.xlsx` a crear.

    Returns:
        La ruta del archivo escrito.
    """
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet, index=False)
    return path


@pytest.fixture
def frames() -> dict[str, pd.DataFrame]:
    """Las 8 hojas de prueba, para modificar antes de escribirlas."""
    return build_frames()


@pytest.fixture
def excel_path(frames: dict[str, pd.DataFrame], tmp_path: Path) -> Path:
    """Un Excel de prueba completo y consistente, en un directorio temporal."""
    return write_workbook(frames, tmp_path / "dataset_test.xlsx")


@pytest.fixture
def database_file(tmp_path: Path) -> Path:
    """La ruta de una base SQLite temporal, todavía sin crear."""
    return tmp_path / "test.db"


@pytest.fixture
def catalog_database(tmp_path: Path) -> Path:
    """Una base temporal con el esquema real y el catálogo de prueba cargado."""
    target = tmp_path / "catalogo_test.db"
    connection = db.connect(target)
    try:
        db.create_schema(connection)
        catalog_data.populate(connection)
    finally:
        connection.close()
    return target


@pytest.fixture
def catalog_connection(catalog_database: Path) -> Iterator[sqlite3.Connection]:
    """Una conexión abierta a la base de prueba del catálogo."""
    connection = db.connect(catalog_database)
    try:
        yield connection
    finally:
        connection.close()
