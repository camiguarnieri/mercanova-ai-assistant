"""Reglas de negocio del carrito: cantidad válida y stock suficiente.

Es el único lugar donde se decide si un producto puede entrar al carrito. Lo
usan las dos puertas de entrada —los endpoints de `cart_api.py` y las
herramientas del modelo de `cart_tools.py`—, así que la regla no se puede
saltear por una de ellas.

La cantidad disponible sale siempre de la base (RF-10): se lee en el momento de
agregar y se vuelve a leer al confirmar la orden. No hay topes escritos a mano.

Los mensajes de error están escritos para que los pueda leer tanto el usuario
como el modelo: dicen qué pasó y con qué número, sin inventar ninguno.
"""

from __future__ import annotations

import sqlite3
from math import isfinite
from typing import Any

from backend import cart_view
from backend.cart_models import Cart
from backend.carts import CartStore

__all__ = [
    "CartError",
    "InvalidQuantityError",
    "ProductUnavailableError",
    "InsufficientStockError",
    "ProductNotInCartError",
    "EmptyCartError",
    "check_quantity",
    "add_item",
    "set_quantity",
    "remove_item",
    "view",
]


class CartError(RuntimeError):
    """Error de la capa del carrito."""


class InvalidQuantityError(CartError):
    """La cantidad pedida no es un número entero mayor a cero."""


class ProductUnavailableError(CartError):
    """El producto existe pero no se puede comprar: está de baja o sin precio."""


class InsufficientStockError(CartError):
    """No hay tantas unidades disponibles como las que se piden."""


class ProductNotInCartError(CartError):
    """Se quiso sacar o cambiar un producto que no está en el carrito."""


class EmptyCartError(CartError):
    """Se quiso confirmar una compra sin productos en el carrito."""


# Convierte la cantidad a entero y rechaza 0, negativos y lo que no es número.
def check_quantity(value: Any) -> int:
    """Valida la cantidad de una línea (RF-17).

    Args:
        value: La cantidad tal como llegó: del frontend o del modelo, que a
            veces la manda como texto.

    Returns:
        La cantidad como entero positivo.

    Raises:
        InvalidQuantityError: Si no es un número, si tiene parte decimal o si
            es 0 o negativa. Un `True` tampoco sirve, aunque Python lo cuente
            como 1.
    """
    if isinstance(value, bool):
        raise InvalidQuantityError(
            f"La cantidad tiene que ser un número entero mayor a 0; llegó {value!r}."
        )
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise InvalidQuantityError(
            f"La cantidad tiene que ser un número entero mayor a 0; llegó {value!r}."
        ) from error
    # 'nan' e 'inf' son números para float() pero no son una cantidad, y sin
    # esto int() los rechazaría con un error que no dice nada.
    if not isfinite(number):
        raise InvalidQuantityError(
            f"La cantidad tiene que ser un número entero mayor a 0; llegó {value!r}."
        )
    if number != int(number):
        raise InvalidQuantityError(
            f"La cantidad tiene que ser un número entero, sin decimales; llegó {value!r}."
        )
    if int(number) <= 0:
        raise InvalidQuantityError(
            f"La cantidad tiene que ser mayor a 0; llegó {int(number)}. Para sacar un "
            f"producto del carrito hay que quitarlo, no pedir 0 unidades."
        )
    return int(number)


# Verifica contra la base que se puedan comprar esas unidades del producto.
def check_stock(connection: sqlite3.Connection, product_id: str, quantity: int) -> int:
    """Comprueba que el producto se pueda comprar en esa cantidad (RF-10).

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto.
        quantity: Unidades que quedarían en la línea del carrito.

    Returns:
        Las unidades disponibles, leídas de la base en este momento.

    Raises:
        catalog.ProductNotFoundError: Si el producto no existe.
        ProductUnavailableError: Si está dado de baja o no tiene precio.
        InsufficientStockError: Si hay menos unidades que las pedidas.
    """
    detail = cart_view.product_for_cart(connection, product_id)
    if not detail.active:
        raise ProductUnavailableError(
            f"{detail.name} está dado de baja en el catálogo y no se puede comprar."
        )
    if detail.current_price is None:
        raise ProductUnavailableError(
            f"{detail.name} no tiene precio cargado en el catálogo, así que no se puede "
            f"agregar al carrito."
        )
    available = detail.available_qty
    if available == 0:
        raise InsufficientStockError(
            f"{detail.name} no tiene stock disponible en ningún depósito, así que no se "
            f"puede agregar al carrito."
        )
    if quantity > available:
        unidades = "unidad disponible" if available == 1 else "unidades disponibles"
        raise InsufficientStockError(
            f"{detail.name}: se pidieron {quantity} unidades y hay {available} "
            f"{unidades}. Se puede agregar hasta {available}."
        )
    return available


# Suma unidades de un producto al carrito de la sesión.
def add_item(
    connection: sqlite3.Connection,
    store: CartStore,
    session_id: str,
    product_id: str,
    quantity: Any = 1,
) -> Cart:
    """Agrega un producto al carrito (RF-09).

    La cantidad se suma a la que ya había, y el stock se valida sobre el total
    de la línea: agregar 3 y después 3 más de un producto con 5 unidades falla,
    como tiene que fallar.

    Args:
        connection: Conexión abierta con `db.connect()`.
        store: Dónde está guardado el carrito.
        session_id: Identificador de la sesión dueña del carrito.
        product_id: Identificador del producto, salido del catálogo.
        quantity: Unidades a sumar.

    Returns:
        El carrito completo después de agregar.

    Raises:
        catalog.ProductNotFoundError: Si el producto no existe.
        InvalidQuantityError: Si la cantidad no sirve.
        ProductUnavailableError: Si el producto no se puede comprar.
        InsufficientStockError: Si no hay stock para el total de la línea.
    """
    wanted = store.quantity(session_id, product_id) + check_quantity(quantity)
    check_stock(connection, product_id, wanted)
    store.set_quantity(session_id, product_id, wanted)
    return view(connection, store, session_id)


# Deja la línea de un producto en una cantidad exacta.
def set_quantity(
    connection: sqlite3.Connection,
    store: CartStore,
    session_id: str,
    product_id: str,
    quantity: Any,
) -> Cart:
    """Cambia la cantidad de un producto que ya está en el carrito (RF-09).

    Args:
        connection: Conexión abierta con `db.connect()`.
        store: Dónde está guardado el carrito.
        session_id: Identificador de la sesión dueña del carrito.
        product_id: Identificador del producto.
        quantity: Cantidad final de la línea.

    Returns:
        El carrito completo después del cambio.

    Raises:
        ProductNotInCartError: Si el producto no está en el carrito.
        InvalidQuantityError: Si la cantidad no sirve.
        InsufficientStockError: Si no hay stock para esa cantidad.
    """
    if store.quantity(session_id, product_id) == 0:
        raise ProductNotInCartError(
            f"El producto '{product_id}' no está en el carrito, así que no se le puede "
            f"cambiar la cantidad. Hay que agregarlo primero."
        )
    wanted = check_quantity(quantity)
    check_stock(connection, product_id, wanted)
    store.set_quantity(session_id, product_id, wanted)
    return view(connection, store, session_id)


# Saca un producto del carrito.
def remove_item(
    connection: sqlite3.Connection, store: CartStore, session_id: str, product_id: str
) -> Cart:
    """Quita un producto del carrito (RF-09).

    Args:
        connection: Conexión abierta con `db.connect()`.
        store: Dónde está guardado el carrito.
        session_id: Identificador de la sesión dueña del carrito.
        product_id: Identificador del producto a quitar.

    Returns:
        El carrito completo después de sacarlo.

    Raises:
        ProductNotInCartError: Si el producto no estaba en el carrito.
    """
    if not store.remove(session_id, product_id):
        raise ProductNotInCartError(
            f"El producto '{product_id}' no está en el carrito, así que no hay nada que "
            f"quitar."
        )
    return view(connection, store, session_id)


# Devuelve el carrito con los datos del catálogo de ahora.
def view(connection: sqlite3.Connection, store: CartStore, session_id: str) -> Cart:
    """Arma el carrito de una sesión (RF-09).

    Args:
        connection: Conexión abierta con `db.connect()`.
        store: Dónde está guardado el carrito.
        session_id: Identificador de la sesión dueña del carrito.

    Returns:
        El carrito con sus líneas, su total y la cantidad de unidades. Una
        sesión sin carrito devuelve uno vacío, no un error.
    """
    return cart_view.build_cart(connection, store, session_id)
