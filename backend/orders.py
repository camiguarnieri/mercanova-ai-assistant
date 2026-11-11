"""Confirmación de la compra e historial de órdenes (RF-14, RF-15, RF-16).

**El modelo no entra acá.** Agregar y quitar del carrito son operaciones
reversibles y las puede hacer él; crear una orden descuenta stock y no se
deshace, así que la ejecuta el usuario desde la interfaz, con la confirmación
explícita que exige `cart_models.CheckoutRequest`. No hay ninguna herramienta
que llegue a estas funciones.

La orden y el descuento de stock se escriben en la misma transacción: si algo
falla, no queda ni la orden ni el stock descontado.

Y toda la secuencia —leer el carrito, validarlo, escribir la orden, vaciarlo—
corre adentro del lock de esa sesión. La transacción sola no alcanzaba: el
carrito vive en la memoria del proceso, así que dos pedidos simultáneos leían el
mismo carrito, los dos pasaban la validación y los dos escribían su orden. El
segundo pedido ahora encuentra el carrito ya vacío y recibe un 409. Está escrito
en `docs/decision-concurrencia-checkout.md`.

Los precios se vuelven a leer del catálogo al confirmar y se copian en la
orden: lo que queda guardado es lo que el usuario confirmó, aunque después el
catálogo cambie.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from backend import cart, cart_view, inventory, orders_sql
from backend.cart_models import Cart, Order, OrderLine
from backend.carts import CartStore

__all__ = ["OrderError", "OrderNotFoundError", "new_order_id", "checkout", "list_orders", "get_order"]


class OrderError(RuntimeError):
    """Error de la capa de órdenes."""


class OrderNotFoundError(OrderError):
    """La orden pedida no existe."""


# Arma un identificador de orden legible y único.
def new_order_id(moment: datetime) -> str:
    """Devuelve el identificador de una orden nueva (RF-14).

    Args:
        moment: El momento en que se confirma la orden.

    Returns:
        Un identificador como `'MN-ORD-20261109-3F2A91C4'`: el prefijo del
        proyecto, la fecha para poder ubicarlo a ojo y ocho caracteres al azar
        para que dos órdenes del mismo día no choquen.
    """
    return f"MN-ORD-{moment.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


# Revisa que el carrito se pueda comprar entero, antes de escribir nada.
def checked_lines(connection: sqlite3.Connection, basket: Cart) -> list[OrderLine]:
    """Valida el carrito y lo convierte en líneas de orden.

    Vuelve a consultar el stock y el precio de cada producto aunque ya se hayan
    validado al agregarlo: entre que se agregó y se confirma pudo cambiar, y la
    orden tiene que salir del estado de ahora (RF-10, RF-15).

    Args:
        connection: Conexión abierta con `db.connect()`.
        basket: El carrito tal como lo armó `cart.view()`.

    Returns:
        Las líneas de la orden, con el precio al momento de confirmar.

    Raises:
        cart.EmptyCartError: Si el carrito está vacío (RF-17).
        cart.InsufficientStockError: Si algún producto ya no tiene stock.
        cart.ProductUnavailableError: Si alguno no se puede comprar.
        OrderError: Si las líneas no están todas en la misma moneda.
    """
    if not basket.items:
        raise cart.EmptyCartError(
            "El carrito está vacío: agregá al menos un producto antes de confirmar la compra."
        )

    lines: list[OrderLine] = []
    for line in basket.items:
        cart.check_stock(connection, line.product_id, line.quantity)
        detail = cart_view.product_for_cart(connection, line.product_id)
        unit_price = float(detail.current_price or 0.0)
        lines.append(
            OrderLine(
                product_id=detail.product_id,
                name=detail.name,
                quantity=line.quantity,
                unit_price=unit_price,
                currency=str(detail.currency),
                line_total=cart_view.money(unit_price * line.quantity),
            )
        )

    currencies = sorted({line.currency for line in lines})
    if len(currencies) > 1:
        raise OrderError(
            f"El carrito tiene productos en {len(currencies)} monedas distintas "
            f"({', '.join(currencies)}) y la compra se confirma en una sola. "
            f"Dejá en el carrito los productos de una moneda y volvé a confirmar."
        )
    return lines


# Confirma la compra: crea la orden, descuenta el stock y vacía el carrito.
def checkout(
    connection: sqlite3.Connection,
    store: CartStore,
    session_id: str,
    *,
    customer_name: str,
    shipping_address: str,
) -> Order:
    """Crea la orden de un carrito confirmado (RF-11 a RF-15).

    Args:
        connection: Conexión abierta con `db.connect()`.
        store: Dónde está guardado el carrito.
        session_id: Identificador de la sesión dueña del carrito.
        customer_name: Nombre de quien recibe el envío.
        shipping_address: Dirección de envío.

    Returns:
        La orden creada, con su identificador, su timestamp y sus líneas.

    Raises:
        cart.EmptyCartError: Si el carrito está vacío.
        cart.InsufficientStockError: Si el stock cambió y ya no alcanza.
        cart.ProductUnavailableError: Si un producto dejó de poder comprarse.
        OrderError: Si el carrito mezcla monedas.
        inventory.StockWriteError: Si el descuento de stock no se pudo hacer
            completo. En ese caso la transacción se deshace entera y el
            carrito queda como estaba.
    """
    # Toda la secuencia va adentro del lock de la sesión: leer el carrito,
    # validarlo, escribir la orden y vaciarlo. La transacción de SQLite sola no
    # alcanza, porque el carrito vive en la memoria del proceso y no en la base:
    # dos pedidos simultáneos leían el mismo carrito, los dos lo validaban y los
    # dos escribían su orden, y el stock se descontaba dos veces.
    #
    # El lock es por sesión: el checkout de otra persona no espera a este.
    with store.session_lock(session_id):
        lines = checked_lines(connection, cart.view(connection, store, session_id))
        created_at = datetime.now(timezone.utc)
        order = Order(
            order_id=new_order_id(created_at),
            session_id=session_id,
            created_at=created_at,
            customer_name=customer_name.strip(),
            shipping_address=shipping_address.strip(),
            currency=lines[0].currency,
            total_amount=cart_view.money(sum(line.line_total for line in lines)),
            items=lines,
        )

        # Una sola transacción: la orden, sus líneas y el descuento de stock
        # entran juntos o no entra nada.
        with connection:
            connection.execute(
                orders_sql.INSERT_ORDER,
                [
                    order.order_id,
                    order.session_id,
                    order.created_at.isoformat(),
                    order.customer_name,
                    order.shipping_address,
                    order.currency,
                    order.total_amount,
                ],
            )
            for line in lines:
                connection.execute(
                    orders_sql.INSERT_ORDER_ITEM,
                    [
                        order.order_id,
                        line.product_id,
                        line.name,
                        line.quantity,
                        line.unit_price,
                        line.currency,
                        line.line_total,
                    ],
                )
                inventory.reduce_stock(connection, line.product_id, line.quantity)

        # Recién con la orden escrita se vacía el carrito: si lo anterior falla,
        # el usuario sigue teniendo lo que había elegido. Y pasa adentro del
        # lock, así el pedido que esté esperando ve el carrito ya vacío y no
        # vuelve a comprar lo mismo.
        store.clear(session_id)
    return order


# Arma las órdenes con sus líneas a partir de las filas de la base.
def orders_from_rows(
    connection: sqlite3.Connection, rows: list[sqlite3.Row]
) -> list[Order]:
    """Convierte filas de `orders` en modelos, con sus líneas adentro.

    Args:
        connection: Conexión abierta con `db.connect()`.
        rows: Las filas de la tabla `orders`, ya ordenadas.

    Returns:
        Las órdenes, en el mismo orden que las filas.
    """
    if not rows:
        return []
    identifiers = [row["order_id"] for row in rows]
    query = orders_sql.ITEMS_OF_ORDERS.format(placeholders=", ".join("?" * len(identifiers)))
    lines: dict[str, list[OrderLine]] = {identifier: [] for identifier in identifiers}
    for item in connection.execute(query, identifiers).fetchall():
        fields = dict(item)
        lines[fields.pop("order_id")].append(OrderLine.model_validate(fields))
    return [
        Order.model_validate({**dict(row), "items": lines[row["order_id"]]}) for row in rows
    ]


# Trae las órdenes de una sesión, de la más nueva a la más vieja.
def list_orders(connection: sqlite3.Connection, session_id: str) -> list[Order]:
    """Devuelve el historial de órdenes de una sesión (RF-16).

    Args:
        connection: Conexión abierta con `db.connect()`.
        session_id: Identificador de la sesión.

    Returns:
        Las órdenes de esa sesión, la más nueva primero. Una lista vacía
        significa que la sesión todavía no compró nada.
    """
    rows = connection.execute(orders_sql.ORDERS_BY_SESSION, [session_id.strip()]).fetchall()
    return orders_from_rows(connection, rows)


# Trae una orden por su identificador.
def get_order(connection: sqlite3.Connection, order_id: str) -> Order:
    """Busca una orden (RF-14).

    Args:
        connection: Conexión abierta con `db.connect()`.
        order_id: Identificador de la orden.

    Returns:
        La orden con sus líneas.

    Raises:
        OrderNotFoundError: Si no existe ninguna orden con ese identificador.
    """
    row = connection.execute(orders_sql.ORDER_BY_ID, [order_id.strip()]).fetchone()
    if row is None:
        raise OrderNotFoundError(
            f"No existe la orden '{order_id}'. Revisá el identificador en el historial "
            f"de órdenes de tu sesión."
        )
    return orders_from_rows(connection, [row])[0]
