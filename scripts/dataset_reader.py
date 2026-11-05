"""Lectura del Excel del dataset: validación de hojas y conversión de tipos.

No toca la base de datos ni el archivo original: solo lo lee y devuelve filas
listas para insertar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

# Hoja del Excel que alimenta cada tabla. Las columnas no se repiten acá: salen
# del esquema SQLite, que es la única fuente de verdad.
SHEET_BY_TABLE: dict[str, str] = {
    "brands": "Brands",
    "categories": "Categories",
    "warehouses": "Warehouses",
    "products": "Products",
    "specifications": "Specifications",
    "pricing": "Pricing",
    "inventory": "Inventory",
    "relations": "Relations",
}

DATE_COLUMNS = frozenset({"launch_date", "price_updated_at"})
DATETIME_COLUMNS = frozenset({"inventory_updated_at"})
BOOLEAN_COLUMNS = frozenset({"active", "tax_included", "pickup_enabled", "shipping_enabled"})


class DatasetError(RuntimeError):
    """Error al procesar el dataset."""


class DatasetFileError(DatasetError):
    """El archivo Excel no se puede abrir."""


class DatasetSheetError(DatasetError):
    """Una hoja falta o no tiene las columnas esperadas."""


# Abre el Excel en modo lectura; no lo modifica.
def open_workbook(excel_path: Path) -> pd.ExcelFile:
    """Abre el Excel del dataset.

    Args:
        excel_path: Ruta del archivo `.xlsx`.

    Returns:
        El workbook de pandas, abierto solo para lectura.

    Raises:
        DatasetFileError: Si el archivo no existe o no se puede leer.
    """
    if not excel_path.is_file():
        raise DatasetFileError(
            f"No se encontró el Excel del dataset en '{excel_path}'. "
            f"Copiá el archivo de la cátedra ahí o pasá la ruta con --excel."
        )
    try:
        return pd.ExcelFile(excel_path)
    except (OSError, ValueError) as error:
        raise DatasetFileError(
            f"No se pudo leer el Excel '{excel_path}'. "
            f"Verificá que sea un .xlsx válido y que no esté abierto en Excel. Detalle: {error}"
        ) from error


# Indica si una celda está realmente vacía.
def is_missing(value: Any) -> bool:
    """Decide si el valor de una celda cuenta como ausente.

    Solo son ausentes la celda vacía, el texto en blanco y los nulos de pandas.
    Un texto como `"None"` o `"NA"` es un valor del catálogo, no un vacío.

    Args:
        value: Valor leído de una celda.

    Returns:
        `True` si no hay dato que guardar.
    """
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))


# Convierte una columna de pandas a valores que SQLite pueda guardar.
def normalize_column(series: pd.Series, column: str) -> list[Any]:
    """Adapta los valores de una columna al tipo que espera SQLite.

    Fechas a texto ISO, booleanos a 0/1, vacíos a `None` y textos sin espacios
    sobrantes. Los tipos de numpy se pasan a tipos nativos de Python, porque
    `sqlite3` no sabe guardarlos.

    Args:
        series: Columna leída del Excel.
        column: Nombre de la columna, para decidir la conversión.

    Returns:
        La lista de valores listos para insertar.
    """
    values: list[Any] = []
    for value in series.tolist():
        if is_missing(value):
            values.append(None)
        elif column in DATE_COLUMNS:
            values.append(value.strftime("%Y-%m-%d"))
        elif column in DATETIME_COLUMNS:
            values.append(value.strftime("%Y-%m-%d %H:%M:%S"))
        elif column in BOOLEAN_COLUMNS:
            values.append(int(bool(value)))
        elif isinstance(value, str):
            values.append(value.strip())
        else:
            values.append(value)
    return values


# Arma las filas de una tabla a partir de su hoja del Excel.
def sheet_rows(
    workbook: pd.ExcelFile, table: str, columns: list[str]
) -> list[tuple[Any, ...]]:
    """Lee la hoja de una tabla y la convierte en filas para insertar.

    Args:
        workbook: Excel abierto con `open_workbook()`.
        table: Nombre de la tabla destino.
        columns: Columnas esperadas, en el orden del esquema.

    Returns:
        Las filas de la hoja, como tuplas en el orden de `columns`.

    Raises:
        DatasetSheetError: Si falta la hoja o alguna columna.
    """
    sheet = SHEET_BY_TABLE[table]
    if sheet not in workbook.sheet_names:
        raise DatasetSheetError(
            f"Falta la hoja '{sheet}' en el Excel. "
            f"Las hojas encontradas son: {', '.join(workbook.sheet_names)}."
        )

    # keep_default_na=False: pandas convierte a NaN textos como "None", "NA" o
    # "NULL", y en este dataset son valores reales del catálogo (por ejemplo
    # "Water Resistance: None"). Acá un vacío es una celda vacía y nada más.
    frame = workbook.parse(sheet, keep_default_na=False, na_values=[])
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise DatasetSheetError(
            f"A la hoja '{sheet}' le faltan columnas que el esquema necesita: "
            f"{', '.join(missing)}. Revisá que el Excel sea el de la cátedra."
        )

    extra = [str(column) for column in frame.columns if column not in columns]
    if extra:
        print(f"  aviso: columnas de '{sheet}' que no están en el esquema: {', '.join(extra)}")

    normalized = [normalize_column(frame[column], column) for column in columns]
    return list(zip(*normalized)) if normalized else []
