"""Conversaciones en curso del asistente, guardadas en la memoria del proceso.

No hay persistencia a propósito: el trabajo pide acompañar una conversación, no
guardar un historial. Lo que esto implica está escrito en `SessionStore`.

Guarda la conversación entera y entera viaja al modelo. Probamos recortarla y la
medición no lo respaldó: está en `docs/decision-recorte-historial.md`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from threading import Lock
from typing import Any

__all__ = ["Message", "SessionStore", "STORE"]

# Un mensaje en el formato de Ollama: rol, contenido y lo que agregue el modelo.
Message = dict[str, Any]


class SessionStore:
    """Guarda la conversación de cada sesión, indexada por `session_id`.

    Vive en la memoria del proceso: **todas las conversaciones se pierden al
    reiniciar la API**, y si se levantan varios workers cada uno tiene las
    suyas. Para este trabajo alcanza; si hiciera falta que sobrevivan, esto se
    reemplaza por una tabla sin tocar el resto del código.

    Los métodos toman un lock porque FastAPI corre los endpoints sincrónicos en
    un threadpool: dos pedidos de la misma pestaña pueden caer en hilos
    distintos y escribir la misma sesión a la vez.
    """

    def __init__(self) -> None:
        self._conversations: dict[str, list[Message]] = {}
        self._products: dict[str, set[str]] = {}
        self._lock = Lock()

    # Devuelve la conversación de una sesión, o None si es la primera vuelta.
    def history(self, session_id: str) -> list[Message] | None:
        """Trae la conversación guardada de una sesión.

        Args:
            session_id: Identificador que mandó el cliente.

        Returns:
            Una copia de los mensajes guardados, o `None` si la sesión no
            existe todavía. Es una copia para que quien la use no modifique lo
            guardado sin pasar por `save()`.
        """
        with self._lock:
            history = self._conversations.get(session_id)
            return list(history) if history is not None else None

    # Reemplaza la conversación de una sesión por la última versión.
    def save(self, session_id: str, history: Sequence[Message]) -> None:
        """Guarda la conversación completa de una sesión.

        Args:
            session_id: Identificador que mandó el cliente.
            history: Los mensajes a guardar, incluido el prompt del sistema.
        """
        with self._lock:
            self._conversations[session_id] = list(history)

    # Devuelve los product_id que aparecieron en resultados de esta sesión.
    def known_products(self, session_id: str) -> set[str]:
        """Trae los identificadores de producto que el modelo ya vio.

        Es lo que hace que no pueda inventar uno: una herramienta solo acepta
        un product_id que haya salido de un resultado anterior de esta misma
        conversación.

        Args:
            session_id: Identificador que mandó el cliente.

        Returns:
            Una copia de los identificadores conocidos, vacía si la sesión es
            nueva.
        """
        with self._lock:
            return set(self._products.get(session_id, ()))

    # Agrega los identificadores que aparecieron en un turno.
    def remember_products(self, session_id: str, products: Iterable[str]) -> None:
        """Guarda los identificadores que el modelo vio en esta sesión.

        Args:
            session_id: Identificador que mandó el cliente.
            products: Los identificadores a recordar. Se suman a los que ya
                había: lo que el modelo vio una vez lo puede seguir usando.
        """
        with self._lock:
            self._products.setdefault(session_id, set()).update(products)

    # Cuántas sesiones hay abiertas; se usa para verificar el comportamiento.
    def count(self) -> int:
        """Devuelve la cantidad de sesiones guardadas."""
        with self._lock:
            return len(self._conversations)


# Instancia única que usa la API. Los tests crean la suya y la inyectan.
STORE = SessionStore()
