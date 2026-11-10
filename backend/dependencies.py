"""Dependencias que comparten los endpoints: la base y las conversaciones.

Están acá, y no en `api.py`, para que los routers las puedan importar sin
depender del módulo que los incluye.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager

from backend import carts, db, sessions, vocabulary

__all__ = [
    "ConnectionScope",
    "get_connection_scope",
    "get_session_store",
    "get_cart_store",
    "get_vocabulary",
]

# Fábrica de conexiones: se llama adentro del endpoint, no antes.
ConnectionScope = Callable[[], AbstractContextManager[sqlite3.Connection]]


def get_connection_scope() -> ConnectionScope:
    """Entrega la fábrica con la que cada endpoint abre su conexión.

    No devuelve una conexión ya abierta a propósito. FastAPI corre las
    dependencias sincrónicas y los endpoints sincrónicos como tareas separadas
    del threadpool, que pueden caer en hilos distintos; una conexión de SQLite
    creada en la dependencia y usada en el endpoint falla con "SQLite objects
    created in a thread can only be used in that same thread". Devolviendo la
    fábrica, cada endpoint abre y cierra la suya en su propio hilo.

    Returns:
        Un callable que da un context manager con la conexión.
    """
    return db.connection_scope


def get_session_store() -> sessions.SessionStore:
    """Entrega el almacén de conversaciones que usa el chat.

    Returns:
        La instancia única del proceso. Los tests la reemplazan con
        `dependency_overrides` para no arrastrar sesiones entre tests.
    """
    return sessions.STORE


def get_cart_store() -> carts.CartStore:
    """Entrega el almacén de carritos que usan el chat y los endpoints del carrito.

    Es el mismo para los dos, así el producto que agrega el asistente es el que
    ve el usuario en pantalla.

    Returns:
        La instancia única del proceso. Los tests la reemplazan con
        `dependency_overrides` para no arrastrar carritos entre tests.
    """
    return carts.STORE


def get_vocabulary() -> vocabulary.Vocabulary:
    """Entrega el vocabulario con el que se arma el esquema del modelo.

    Returns:
        La instancia única del proceso. Los tests la reemplazan para que el
        esquema salga de la base de prueba y no de la real.
    """
    return vocabulary.VOCABULARY
