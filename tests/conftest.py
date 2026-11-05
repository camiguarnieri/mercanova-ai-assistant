"""Fixtures compartidas: datos de prueba y un Excel mínimo, armado en el test.

Ningún test lee el Excel de la cátedra ni la base real: todo se genera acá.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
