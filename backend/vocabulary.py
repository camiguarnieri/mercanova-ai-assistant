"""El vocabulario del catálogo que viaja en el esquema de las herramientas.

Las categorías y los casos de uso válidos salen de la base, no de una lista
escrita a mano: si se carga otro dataset, el esquema que recibe el modelo
cambia solo. Se arman una vez y se guardan, porque el esquema viaja en cada
pedido al modelo y el catálogo no cambia mientras corre la API.
"""

from __future__ import annotations

from sqlite3 import Connection
from threading import Lock
from typing import Any

from backend import catalog, tool_schemas

__all__ = ["Vocabulary", "VOCABULARY"]


class Vocabulary:
    """Las definiciones de las herramientas, con los valores del catálogo.

    Se arman la primera vez que se las pide y quedan guardadas en memoria. La
    API las pide al arrancar para que el primer mensaje no pague las consultas,
    pero si en ese momento la base todavía no estaba cargada se vuelven a
    intentar en el primer uso, así no quedan vacías hasta el próximo reinicio.

    Toma un lock porque los endpoints sincrónicos corren en un threadpool: dos
    pedidos a la vez armarían el esquema dos veces.
    """

    def __init__(self) -> None:
        self._schemas: list[dict[str, Any]] | None = None
        self._lock = Lock()

    # Devuelve los esquemas con el vocabulario, armándolos la primera vez.
    def schemas(self, connection: Connection) -> list[dict[str, Any]]:
        """Trae las definiciones de las herramientas para mandarle al modelo.

        Args:
            connection: Conexión abierta con `db.connect()`, válida en este
                hilo. Se usa solo la primera vez.

        Returns:
            Las cinco definiciones, con las categorías y los casos de uso del
            catálogo listados en los filtros.

        Raises:
            sqlite3.Error: Si la base no se puede consultar. Quien llama decide
                qué hacer: al arrancar es una advertencia, y en una
                conversación el error ya lo traduce `tool_router`.
        """
        with self._lock:
            if self._schemas is None:
                self._schemas = tool_schemas.build_tool_schemas(
                    catalog.list_category_names(connection),
                    catalog.list_use_cases_by_category(connection),
                )
            return self._schemas


# Instancia única que usa la API. Los tests crean la suya y la inyectan.
VOCABULARY = Vocabulary()
