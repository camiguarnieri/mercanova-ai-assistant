"""Arma la vista del carrito leyendo el catálogo en el momento.

El carrito guardado son cantidades (`carts.py`). Todo lo demás —nombre, marca,
precio, stock, totales— sale de una consulta a la base cada vez que se arma
esta vista, igual que cualquier otro dato que la aplicación afirma.

Acá no hay reglas de negocio: no se valida stock ni cantidad, eso es de
`cart.py`. Si el stock bajó después de agregar el producto, la línea lo muestra
en `available_qty` y la regla la aplica quien corresponda.
"""

from __future__ import annotations

import sqlite3

from backend import catalog
from backend.cart_models import Cart, CartLine
from backend.carts import CartStore
from backend.models import ProductDetail

__all__ = ["CENTS", "money", "product_for_cart", "cart_line", "build_cart"]

# Los precios del catálogo vienen con dos decimales; los totales también.
CENTS = 2


# Redondea un importe a dos decimales.
def money(amount: float) -> float:
    """Deja un importe con la precisión con la que se muestra.

    Args:
        amount: El importe calculado.

    Returns:
        El importe redondeado a `CENTS` decimales, para que la suma de las
        líneas y el total no difieran por el binario flotante.
    """
    return round(amount, CENTS)


# Trae del catálogo el producto de una línea del carrito.
def product_for_cart(connection: sqlite3.Connection, product_id: str) -> ProductDetail:
    """Busca el producto de una línea en el catálogo.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto.

    Returns:
        La ficha del producto, con su precio y su stock de ahora.

    Raises:
        catalog.ProductNotFoundError: Si el producto no existe (RF-17).
    """
    return catalog.get_product(connection, product_id)


# Arma una línea del carrito con el dato actual del producto.
def cart_line(detail: ProductDetail, quantity: int) -> CartLine:
    """Convierte un producto y su cantidad en una línea del carrito.

    Args:
        detail: La ficha del producto, recién leída del catálogo.
        quantity: Unidades de ese producto en el carrito.

    Returns:
        La línea, con el precio por unidad y el total de la línea. Si el
        catálogo no tiene el precio cargado, los dos viajan en null: no se
        estima un importe.
    """
    unit_price = detail.current_price
    return CartLine(
        product_id=detail.product_id,
        name=detail.name,
        brand=detail.brand,
        quantity=quantity,
        currency=detail.currency,
        unit_price=unit_price,
        line_total=None if unit_price is None else money(unit_price * quantity),
        available_qty=detail.available_qty,
    )


# Arma el carrito completo de una sesión, con sus totales.
def build_cart(
    connection: sqlite3.Connection, store: CartStore, session_id: str
) -> Cart:
    """Devuelve el carrito de una sesión con los datos del catálogo.

    Args:
        connection: Conexión abierta con `db.connect()`.
        store: Dónde están guardadas las cantidades.
        session_id: Identificador de la sesión dueña del carrito.

    Returns:
        El carrito, con una línea por producto y el total sumado por el
        sistema. Un producto que ya no está en el catálogo se saltea: no se
        puede mostrar su precio, y dejarlo trabaría el carrito entero.
    """
    lines: list[CartLine] = []
    for product_id, quantity in store.items(session_id).items():
        try:
            detail = product_for_cart(connection, product_id)
        except catalog.ProductNotFoundError:
            continue
        lines.append(cart_line(detail, quantity))

    priced = [line for line in lines if line.line_total is not None]
    return Cart(
        session_id=session_id,
        items=lines,
        currency=priced[0].currency if priced else None,
        total=money(sum(line.line_total or 0.0 for line in lines)),
        item_count=sum(line.quantity for line in lines),
    )
