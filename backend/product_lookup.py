"""Busca en el catálogo los productos que el usuario nombra, antes del modelo.

Tres rondas de prueba con dos modelos distintos y ninguno busca un producto que
el usuario nombra: contesta "no tengo información" sin consultar nada. Dejamos
de pedírselo al prompt y lo resolvemos acá.

Antes del turno del modelo se revisa el mensaje contra los nombres del catálogo
y el resultado se inyecta en la conversación como un mensaje de herramienta. Si
hay coincidencia, el modelo arranca con el dato; si el usuario nombró algo que
no está, arranca con la constancia de que el sistema lo buscó y no existe, así
una afirmación de ausencia también queda respaldada por una consulta.

## La heurística

1. **Coincidencia exacta del nombre del catálogo dentro del mensaje**, sin
   distinguir mayúsculas y con los espacios normalizados. La comparación la
   hace SQLite: `? LIKE '%' || name || '%'`, con el mensaje como sujeto y el
   nombre como patrón. Son 360 nombres y una sola consulta.
2. Si no coincide ninguno, se busca un **candidato a nombre propio** en el
   mensaje: una tirada de dos o más palabras seguidas que incluya al menos dos
   palabras con mayúscula. Eso distingue "¿tenés el iPhone 15 Pro?" de "quiero
   auriculares para viajar", y es lo que decide si se inyecta la ausencia o no
   se inyecta nada.

## Qué no detecta

- Un nombre escrito a medias: "el Dock Hub" no encuentra "Aether Dock Hub 7".
- Un nombre con un error de tipeo o sin la marca: "Dock Hub 7 de Aether".
- Un nombre todo en minúscula que no esté completo: sin coincidencia exacta y
  sin mayúsculas, no hay candidato y no se inyecta nada.
- Un producto nombrado por su categoría y una característica, que es el caso
  que el modelo sí resuelve buscando con filtros.

En esos casos el turno queda como antes: el modelo tiene que buscar, y las
reglas del prompt y la procedencia de los product_id siguen tapando el resto.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from backend import catalog_sql, catalog_text
from backend.models import ProductSummary

__all__ = ["TOOL_NAME", "find_products", "name_candidate", "lookup_message"]

# Con qué nombre se muestra esta consulta en la traza de la interfaz. No es una
# herramienta del esquema: la corre el sistema, no el modelo.
TOOL_NAME = "lookup_product_name"

# Cuántos productos se inyectan si el mensaje nombra más de uno.
MAX_MATCHES = 3

# Palabras con mayúscula que no son parte de un nombre de producto.
IGNORED_WORDS = frozenset({"USD", "UYU", "IVA", "OK"})


# Busca los productos cuyo nombre aparece en el mensaje.
def find_products(
    connection: sqlite3.Connection, message: str, limit: int = MAX_MATCHES
) -> list[ProductSummary]:
    """Busca en el catálogo los nombres que aparecen en el mensaje.

    Args:
        connection: Conexión abierta con `db.connect()`.
        message: Lo que escribió el usuario.
        limit: Cuántos productos devolver como máximo.

    Returns:
        Los resúmenes de los productos activos cuyo nombre está contenido en el
        mensaje, del nombre más largo al más corto, porque el más largo es el
        más específico. Vacío si ninguno coincide.
    """
    text = " ".join(message.split())
    if not text:
        return []
    rows = connection.execute(
        f"SELECT {catalog_sql.ASSISTANT_COLUMNS} {catalog_sql.PRODUCT_SOURCE} "
        f"WHERE p.active = 1 AND ? LIKE '%' || p.name || '%' "
        f"ORDER BY LENGTH(p.name) DESC, p.name LIMIT ?",
        [text, limit],
    ).fetchall()
    return [ProductSummary.model_validate(dict(row)) for row in rows]


# Busca en el mensaje algo que parezca el nombre de un producto.
def name_candidate(message: str) -> str | None:
    """Saca del mensaje la tirada de palabras que parece un nombre propio.

    Sirve para distinguir "¿tenés el iPhone 15 Pro?", donde el usuario nombró
    un producto que no existe, de "quiero auriculares para viajar", donde no
    nombró ninguno. Pide dos palabras con mayúscula para no confundir la
    mayúscula del principio de la oración ni un precio con moneda.

    Args:
        message: Lo que escribió el usuario.

    Returns:
        El candidato, o `None` si el mensaje no nombra nada que parezca un
        producto.
    """
    tokens = [token for token in re.split(r"[^\w./-]+", message, flags=re.UNICODE) if token]
    best: list[str] = []
    current: list[str] = []
    for token in tokens:
        if looks_like_a_name_part(token):
            current.append(token)
        else:
            best = longest(best, current)
            current = []
    best = longest(best, current)
    return " ".join(best) if best else None


# Dice si una palabra puede ser parte de un nombre de producto.
def looks_like_a_name_part(token: str) -> bool:
    """Acepta las palabras con mayúscula y los números de modelo."""
    if token.upper() in IGNORED_WORDS:
        return False
    if token.isdigit():
        return True
    return any(letter.isupper() for letter in token)


# Devuelve la tirada que tenga al menos dos palabras con mayúscula.
def longest(best: list[str], current: list[str]) -> list[str]:
    """Elige la tirada más larga que pueda ser un nombre.

    Args:
        best: La mejor tirada hasta ahora.
        current: La tirada que se acaba de cerrar.

    Returns:
        La que sirva: necesita dos palabras o más y al menos dos con mayúscula,
        que es lo que descarta "Quiero una notebook" y "hasta 200 USD".
    """
    with_capitals = [token for token in current if not token.isdigit()]
    if len(current) < 2 or len(with_capitals) < 2:
        return best
    return current if len(current) > len(best) else best


# Arma el mensaje de herramienta que se inyecta en la conversación.
def lookup_message(
    connection: sqlite3.Connection, message: str
) -> dict[str, Any] | None:
    """Revisa el mensaje del usuario contra el catálogo.

    Args:
        connection: Conexión abierta con `db.connect()`.
        message: Lo que escribió el usuario.

    Returns:
        El resultado listo para inyectar, o `None` si el mensaje no nombra
        ningún producto y no hay nada que consultar. Cuando hay coincidencia
        trae los productos; cuando el usuario nombró algo que no está, lo dice
        con el nombre que escribió.
    """
    found = find_products(connection, message)
    if found:
        return {
            "found": True,
            "source": "El sistema buscó en el catálogo el nombre que escribió el usuario.",
            "total": len(found),
            # Los campos de usos van escritos, igual que en las herramientas.
            "products": [
                catalog_text.with_uses_text(product.model_dump(mode="json"))
                for product in found
            ],
        }

    candidate = name_candidate(message)
    if candidate is None:
        return None
    return {
        "found": False,
        "source": "El sistema buscó en el catálogo el nombre que escribió el usuario.",
        "searched": candidate,
        "products": [],
        "message": (
            f"Ningún producto activo del catálogo se llama '{candidate}'. Podés decirle "
            f"al usuario que no está, y ofrecerle buscar por categoría o por marca."
        ),
    }
