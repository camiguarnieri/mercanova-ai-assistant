"""Carritos en curso, guardados en la memoria del proceso, uno por sesión.

Mismo criterio que `sessions.py`: el carrito acompaña una conversación, no es
un historial. **Se pierde al reiniciar la API.** Lo que sí sobrevive es la
orden, que se guarda en la base cuando el usuario confirma.

Acá no hay reglas de negocio: esto solo guarda `{product_id: cantidad}`. La
validación de stock y el armado del carrito con precios están en `cart.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock

__all__ = ["CartStore", "CartSession", "STORE"]


class CartStore:
    """Guarda el carrito de cada sesión, indexado por `session_id`.

    Guarda **solo cantidades por producto**, nunca precios ni nombres: esos se
    leen de la base cada vez que se muestra el carrito, así el usuario no ve un
    precio viejo.

    Los métodos toman un lock por lo mismo que `SessionStore`: FastAPI corre los
    endpoints sincrónicos en un threadpool y dos pedidos de la misma pestaña
    pueden escribir el mismo carrito a la vez.

    Ese lock hace que cada método sea atómico, que no es lo mismo que hacer
    atómica una secuencia de varios. Para eso está `session_lock()`, que usa el
    checkout.
    """

    def __init__(self) -> None:
        self._carts: dict[str, dict[str, int]] = {}
        self._lock = Lock()
        # Un lock por sesión, para las operaciones que son varios pasos. Está
        # aparte de `_lock`: ese se toma por microsegundos para tocar los
        # diccionarios, y estos se mantienen tomados durante toda una operación,
        # que adentro vuelve a llamar a los métodos de acá.
        self._session_locks: dict[str, Lock] = {}

    # Devuelve las cantidades por producto de una sesión.
    def items(self, session_id: str) -> dict[str, int]:
        """Trae el contenido del carrito de una sesión.

        Args:
            session_id: Identificador que mandó el cliente.

        Returns:
            Una copia de `{product_id: cantidad}`, en el orden en que se
            agregaron los productos. Vacío si la sesión no tiene carrito.
        """
        with self._lock:
            return dict(self._carts.get(session_id, {}))

    # Devuelve cuántas unidades de un producto hay ya en el carrito.
    def quantity(self, session_id: str, product_id: str) -> int:
        """Trae la cantidad de un producto en el carrito.

        Args:
            session_id: Identificador que mandó el cliente.
            product_id: Identificador del producto.

        Returns:
            Las unidades que ya hay, o 0 si el producto no está en el carrito.
        """
        with self._lock:
            return self._carts.get(session_id, {}).get(product_id, 0)

    # Fija la cantidad de un producto; con 0 lo saca.
    def set_quantity(self, session_id: str, product_id: str, quantity: int) -> None:
        """Deja la línea de un producto en la cantidad indicada.

        Args:
            session_id: Identificador que mandó el cliente.
            product_id: Identificador del producto.
            quantity: Cantidad final de la línea. Con 0 o menos, la línea se
                saca: un carrito no guarda líneas en cero.
        """
        with self._lock:
            cart = self._carts.setdefault(session_id, {})
            if quantity <= 0:
                cart.pop(product_id, None)
            else:
                cart[product_id] = quantity

    # Saca un producto del carrito y dice si estaba.
    def remove(self, session_id: str, product_id: str) -> bool:
        """Saca la línea de un producto.

        Args:
            session_id: Identificador que mandó el cliente.
            product_id: Identificador del producto.

        Returns:
            `True` si el producto estaba en el carrito, `False` si no. Quien
            llama decide si eso es un error: sacar algo que no está es un caso
            borde del RF-17, no una falla del almacén.
        """
        with self._lock:
            return self._carts.setdefault(session_id, {}).pop(product_id, None) is not None

    # Vacía el carrito de una sesión, por ejemplo después de confirmar la orden.
    def clear(self, session_id: str) -> None:
        """Deja el carrito de una sesión sin productos.

        Args:
            session_id: Identificador que mandó el cliente.
        """
        with self._lock:
            self._carts.pop(session_id, None)

    # Deja pasar una sola operación por vez sobre el carrito de una sesión.
    @contextmanager
    def session_lock(self, session_id: str) -> Iterator[None]:
        """Serializa las operaciones de varios pasos sobre un mismo carrito.

        Los métodos de esta clase son atómicos de a uno, pero una operación que
        lee el carrito, decide algo y después lo escribe no lo es: entre la
        lectura y la escritura puede entrar otro pedido. El checkout es el caso
        que importa, porque su escritura no se puede deshacer.

        **El lock es por sesión y no uno global**: dos sesiones distintas toman
        locks distintos y no se esperan entre ellas, así una compra no hace fila
        detrás de la de otra persona.

        Se libera al salir del bloque, también si lo que pasó adentro falló: es
        un `with` sobre un `Lock`, no un par de llamadas a mano.

        No hay riesgo de deadlock con SQLite: adentro del bloque siempre se toma
        primero este lock y después el de la base, nunca al revés, y un hilo
        tiene como máximo un lock de sesión, así que no hay espera circular.

        Args:
            session_id: Identificador de la sesión dueña del carrito.

        Yields:
            Nada: lo que importa es el bloque, no un valor.
        """
        # El `_lock` se toma solo para buscar o crear el lock de la sesión, y se
        # suelta antes de esperarlo: si se lo mantuviera, un checkout en curso
        # bloquearía a todas las demás sesiones y esto sería un lock global con
        # pasos extra.
        with self._lock:
            lock = self._session_locks.setdefault(session_id, Lock())
        with lock:
            yield

    # Cuántos carritos hay abiertos; se usa para verificar el comportamiento.
    def count(self) -> int:
        """Devuelve la cantidad de sesiones con carrito guardado."""
        with self._lock:
            return len(self._carts)


@dataclass(frozen=True)
class CartSession:
    """El carrito de una sesión concreta: el almacén junto al `session_id`.

    Existe para que las herramientas del modelo reciban un solo parámetro
    además de la conexión, igual que las del catálogo. El `session_id` no es un
    argumento de la herramienta: lo pone el servidor con la sesión del pedido,
    así el modelo no puede tocar el carrito de otra conversación.
    """

    store: CartStore
    session_id: str


# Instancia única que usa la API. Los tests crean la suya y la inyectan.
STORE = CartStore()
