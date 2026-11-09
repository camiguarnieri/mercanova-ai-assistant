"""Las dos herramientas del carrito que el LLM puede invocar.

El modelo puede agregar y quitar productos: son operaciones reversibles y el
usuario ve el carrito en pantalla. **No puede confirmar la compra**: eso lo
hace el usuario desde la interfaz y está en `orders.py`, sin herramienta que
llegue hasta ahí.

Valen las mismas garantías que para las herramientas del catálogo:

- el `product_id` tiene que haber salido de un resultado de esta conversación,
  que lo revisa `provenance.check_ids()` antes de ejecutar;
- el stock lo valida `cart.py` contra la base, no el modelo;
- lo que vuelve al modelo no trae cantidades de stock. La única herramienta que
  devuelve unidades disponibles sigue siendo `check_availability`.

El total del carrito lo calcula el sistema con los precios del catálogo y viaja
escrito en el mensaje: el modelo lo repite, no lo suma.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend import cart
from backend.cart_models import Cart
from backend.carts import CartSession

__all__ = ["cart_for_the_model", "cart_message", "add_to_cart", "remove_from_cart"]


# Arma la vista del carrito que puede leer el modelo.
def cart_for_the_model(basket: Cart) -> dict[str, Any]:
    """Recorta el carrito a lo que el modelo necesita leer.

    Deja afuera `available_qty` de cada línea: es una cantidad de stock, y la
    regla del proyecto es que un número de stock solo sale de
    `check_availability`, que lo consulta en el momento. Con la cantidad acá, el
    modelo la repetiría turnos después como si la hubiera vuelto a consultar.

    Args:
        basket: El carrito como lo arma `cart.view()`.

    Returns:
        Las líneas con su cantidad y sus precios, el total y las unidades.
    """
    return {
        "items": [
            {
                "product_id": line.product_id,
                "name": line.name,
                "quantity": line.quantity,
                "currency": line.currency,
                "unit_price": line.unit_price,
                "line_total": line.line_total,
            }
            for line in basket.items
        ],
        "currency": basket.currency,
        "total": basket.total,
        "item_count": basket.item_count,
    }


# Escribe en una línea cómo quedó el carrito, para que el modelo lo repita.
def cart_message(basket: Cart) -> str:
    """Arma la frase con el estado del carrito.

    El total va escrito con su moneda y atado al carrito, por lo mismo que el
    stock va con el nombre del producto en `tools.stock_message()`: el modelo
    repite estas frases casi literales.

    Args:
        basket: El carrito como lo arma `cart.view()`.

    Returns:
        La frase con las unidades y el total, o que el carrito quedó vacío.
    """
    if not basket.items:
        return "El carrito quedó vacío."
    unidades = "unidad" if basket.item_count == 1 else "unidades"
    productos = "producto" if len(basket.items) == 1 else "productos"
    total = f"{basket.currency} {basket.total:.2f}" if basket.currency else "sin precio"
    return (
        f"El carrito tiene {basket.item_count} {unidades} de {len(basket.items)} "
        f"{productos} y suma {total}."
    )


# Agrega unidades de un producto al carrito de esta conversación.
def add_to_cart(
    connection: sqlite3.Connection,
    session: CartSession,
    product_id: str,
    quantity: Any = 1,
) -> dict[str, Any]:
    """Agrega un producto al carrito (RF-09, RF-10).

    Args:
        connection: Conexión abierta con `db.connect()`.
        session: El carrito de esta conversación, que pone el servidor.
        product_id: Identificador del producto, salido de un resultado
            anterior de esta conversación.
        quantity: Unidades a sumar a las que ya haya.

    Returns:
        Cómo quedó el carrito, con el total calculado por el sistema.

    Raises:
        cart.CartError: Si la cantidad no sirve o no hay stock. `run_tool` la
            traduce a un resultado con `error` para que lo lea el modelo.
        catalog.ProductNotFoundError: Si el producto no existe.
    """
    basket = cart.add_item(
        connection, session.store, session.session_id, product_id, quantity
    )
    added = next(
        (line for line in basket.items if line.product_id == product_id), None
    )
    agregado = f"{added.quantity} x {added.name} en el carrito" if added else "agregado"
    return {
        "found": True,
        "message": f"Listo: {agregado}. {cart_message(basket)}",
        "cart": cart_for_the_model(basket),
    }


# Saca un producto del carrito de esta conversación.
def remove_from_cart(
    connection: sqlite3.Connection, session: CartSession, product_id: str
) -> dict[str, Any]:
    """Quita un producto del carrito (RF-09).

    Saca la línea entera, con todas sus unidades. Para dejar menos unidades, el
    usuario cambia la cantidad desde el carrito.

    Args:
        connection: Conexión abierta con `db.connect()`.
        session: El carrito de esta conversación, que pone el servidor.
        product_id: Identificador del producto a quitar.

    Returns:
        Cómo quedó el carrito después de sacarlo.

    Raises:
        cart.ProductNotInCartError: Si el producto no estaba en el carrito.
    """
    basket = cart.remove_item(connection, session.store, session.session_id, product_id)
    return {
        "found": True,
        "message": f"Listo: saqué '{product_id}' del carrito. {cart_message(basket)}",
        "cart": cart_for_the_model(basket),
    }
