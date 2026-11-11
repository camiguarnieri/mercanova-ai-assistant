"""Deja el catálogo cargado antes de que arranque el servidor, en el contenedor.

Lo corre `entrypoint.sh` en cada arranque, y es idempotente: mira si la base ya
tiene productos y solo carga el Excel si está vacía. La base vive en un volumen,
así que la carga pasa una sola vez —el primer `docker compose up`— y los
reinicios siguientes la encuentran hecha.

Decidir por "¿hay productos?" y no por "¿existe el archivo?" es a propósito: el
archivo lo crea `db.connect()` con solo abrirlo, así que su existencia no dice
nada. Las filas de `products` sí.

No reemplaza a `scripts/load_dataset.py`: lo llama. La carga sigue viviendo en
un solo lugar, y el camino manual la sigue corriendo a mano como siempre.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db, environment  # noqa: E402  (después de ajustar sys.path)
from scripts.dataset_reader import DatasetError  # noqa: E402
from scripts.load_dataset import load_dataset  # noqa: E402

# Donde el Dockerfile deja el Excel del dataset.
DEFAULT_EXCEL = Path("/app/dataset/MercaNova_dataset.xlsx")


# Cuenta los productos cargados, creando el esquema si la base es nueva.
def loaded_products() -> int:
    """Dice cuántos productos hay en la base.

    Crea el esquema si falta, así la cuenta funciona también sobre una base
    recién creada. Es la misma operación idempotente que hace la carga.

    Returns:
        La cantidad de filas en `products`. 0 si la base está vacía.

    Raises:
        DatabaseError: Si la base no se puede abrir o el esquema no se aplica.
    """
    with db.connection_scope() as connection:
        db.create_schema(connection)
        connection.commit()
        return db.table_counts(connection)["products"]


# Carga el catálogo si la base está vacía; si no, no hace nada.
def main() -> int:
    """Asegura que el catálogo esté cargado.

    Returns:
        0 si la base quedó con el catálogo cargado —ya lo estaba o se cargó
        ahora—, 1 si la carga falló.
    """
    environment.load_env_file()
    target = db.database_path()

    try:
        products = loaded_products()
    except db.DatabaseError as error:
        print(f"Error al abrir la base de datos: {error}", file=sys.stderr)
        return 1

    if products > 0:
        print(f"Catálogo ya cargado en '{target}': {products} productos.")
        return 0

    excel = Path(os.getenv("DATASET_EXCEL") or DEFAULT_EXCEL)
    print(f"La base '{target}' está vacía. Cargando el catálogo desde '{excel}'...")
    try:
        counts = load_dataset(excel)
    except (DatasetError, db.DatabaseError) as error:
        print(f"Error al cargar el catálogo: {error}", file=sys.stderr)
        return 1

    print(f"Catálogo cargado: {sum(counts.values())} filas en {len(counts)} tablas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
