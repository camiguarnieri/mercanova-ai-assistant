"""Ayuda al modelo a armar bien una búsqueda del catálogo.

Dos cosas, las dos para que no se rinda ni le invente una respuesta al usuario:
revisar los filtros contra el vocabulario antes de consultar, y explicar una
búsqueda vacía con los valores que sí existen.

No levanta excepciones ni ejecuta la búsqueda: devuelve texto y datos, y
`tools.py` decide qué hacer con ellos.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

from backend import catalog

__all__ = ["filter_problems", "filter_error", "empty_result"]


# Dice si un valor está en el vocabulario, sin distinguir mayúsculas.
def is_valid(value: str, valid: Sequence[str]) -> bool:
    """Compara un filtro contra los valores del catálogo.

    Args:
        value: El valor que mandó el modelo.
        valid: Los valores que existen en el catálogo.

    Returns:
        `True` si el valor existe. No distingue mayúsculas porque la búsqueda
        tampoco lo hace: 'headphones' y 'Headphones' traen lo mismo.
    """
    return value.strip().casefold() in {option.casefold() for option in valid}


# Junta todo lo que está mal en los filtros, en vez de cortar en el primero.
def filter_problems(
    connection: sqlite3.Connection,
    *,
    category: str | None = None,
    recommended_for: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> list[str]:
    """Revisa los filtros contra el vocabulario y el sentido común.

    Se revisa todo de una porque cada vuelta al modelo cuesta segundos de CPU:
    si mandó mal el precio y además un caso de uso que no existe, tiene que
    enterarse de las dos cosas en la misma respuesta.

    Args:
        connection: Conexión abierta con `db.connect()`.
        category: Categoría que mandó el modelo.
        recommended_for: Caso de uso que mandó el modelo.
        min_price: Precio vigente mínimo.
        max_price: Precio vigente máximo.

    Returns:
        Un problema por cada filtro que está mal, con los valores válidos
        adentro del mensaje. Vacío si se puede buscar.
    """
    problems: list[str] = []

    # Un modelo chico manda los dos extremos iguales cuando el usuario dijo un
    # solo número, y así deja afuera todo lo que no cueste exactamente eso.
    if min_price is not None and max_price is not None and min_price == max_price:
        problems.append(
            f"min_price y max_price no pueden ser iguales, y los dos llegaron en "
            f"{min_price:g}: si el usuario dio un tope mandá solo max_price, y si dio "
            f"un piso solo min_price."
        )

    if category is not None:
        valid = catalog.list_category_names(connection)
        if not is_valid(category, valid):
            problems.append(
                f"La categoría '{category}' no existe en el catálogo. Las que hay son: "
                f"{', '.join(valid)}."
            )

    if recommended_for is not None:
        problems.extend(use_case_problems(connection, category, recommended_for))

    return problems


# Revisa el caso de uso, contra el catálogo y contra la categoría buscada.
def use_case_problems(
    connection: sqlite3.Connection, category: str | None, recommended_for: str
) -> list[str]:
    """Revisa que el caso de uso exista, y que exista en esa categoría.

    Los casos de uso no son globales: 'video calls' existe en Webcams y no en
    Headphones. Dos valores válidos pueden no traer nada juntos, y entonces lo
    que le sirve al modelo son los casos de uso de esa categoría, no los del
    catálogo entero.

    Args:
        connection: Conexión abierta con `db.connect()`.
        category: Categoría que mandó el modelo, si mandó alguna.
        recommended_for: Caso de uso que mandó el modelo.

    Returns:
        El problema que tenga el caso de uso, o una lista vacía.
    """
    valid = catalog.list_use_cases(connection)
    if not is_valid(recommended_for, valid):
        return [
            f"El caso de uso '{recommended_for}' no existe en el catálogo. Los que hay "
            f"son: {', '.join(valid)}. Si ninguno es lo que pidió el usuario, no mandes "
            f"recommended_for y filtrá solo por categoría."
        ]

    if category is None:
        return []
    in_category = catalog.list_use_cases(connection, category)
    if in_category and not is_valid(recommended_for, in_category):
        return [
            f"La categoría '{category}' no tiene productos para '{recommended_for}'. "
            f"Sus casos de uso son: {', '.join(in_category)}. Usá uno de esos, o buscá "
            f"sin recommended_for y mirá el campo recommended_for de cada resultado."
        ]
    return []


# Arma el mensaje con todos los problemas, listo para que el modelo lo lea.
def filter_error(
    connection: sqlite3.Connection,
    *,
    category: str | None = None,
    recommended_for: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> str | None:
    """Revisa los filtros y devuelve qué hay que corregir.

    Args:
        connection: Conexión abierta con `db.connect()`.
        category: Categoría que mandó el modelo.
        recommended_for: Caso de uso que mandó el modelo.
        min_price: Precio vigente mínimo.
        max_price: Precio vigente máximo.

    Returns:
        El mensaje con todos los problemas juntos, o `None` si los filtros
        sirven y se puede buscar.
    """
    problems = filter_problems(
        connection,
        category=category,
        recommended_for=recommended_for,
        min_price=min_price,
        max_price=max_price,
    )
    if not problems:
        return None
    return (
        "No se puede buscar con esos filtros. "
        + " ".join(problems)
        + " Corregí lo que esté mal y buscá de nuevo."
    )


# Arma la respuesta de una búsqueda sin resultados, con cómo reintentarla.
def empty_result(
    connection: sqlite3.Connection, filters: dict[str, Any]
) -> dict[str, Any]:
    """Explica una búsqueda vacía y devuelve con qué se puede reintentar.

    Acá los filtros ya son válidos: no hay productos que los cumplan todos
    juntos. Devolver solo "no hay nada" hace que el modelo le diga al usuario
    que el catálogo no tiene lo que busca, cuando lo que sobra es un filtro.
    Los valores válidos se devuelven únicamente para los filtros que se usaron:
    lo que no se mandó no puede estar mal, y cada lista ocupa contexto.

    Args:
        connection: Conexión abierta con `db.connect()`.
        filters: Los filtros tal como se usaron, incluidos los vacíos.

    Returns:
        El resultado con `found` en `False`, los filtros aplicados y los
        valores válidos de los filtros que podrían sobrar.
    """
    applied = {name: value for name, value in filters.items() if value is not None}
    result: dict[str, Any] = {
        "found": False,
        "total": 0,
        "products": [],
        "filters_used": applied,
        "message": (
            "No hay productos en el catálogo que cumplan todos esos filtros juntos. "
            "Sacá el que sobre y buscá de nuevo; no le digas al usuario que no hay "
            "nada sin volver a intentar."
        ),
    }
    if "category" in applied:
        result["valid_categories"] = catalog.list_category_names(connection)
    if "recommended_for" in applied:
        # Si se filtró por categoría, los que le sirven son los de esa
        # categoría: los del catálogo entero lo mandarían a combinar de nuevo
        # dos valores que juntos no traen nada.
        result["valid_recommended_for"] = catalog.list_use_cases(
            connection, applied.get("category")
        ) or catalog.list_use_cases(connection)
    if "search" in applied:
        result["note_about_search"] = (
            "El parámetro search busca texto del catálogo, que está en inglés. Si le "
            "mandaste la frase del usuario en español, sacalo y filtrá con category y "
            "recommended_for."
        )
    return result
