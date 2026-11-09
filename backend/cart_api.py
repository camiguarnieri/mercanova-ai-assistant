"""Endpoints del carrito, del checkout y del historial de órdenes.

Solo traduce el pedido HTTP: las reglas están en `cart.py` y la confirmación de
la compra en `orders.py`. Los errores de esas capas los traduce `api.py`.

El checkout es el único lugar donde nace una orden, y pide `confirmed: true`
además de los datos de envío (RF-12): el asistente no tiene ninguna herramienta
que llegue hasta acá.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from backend import cart, carts, orders
from backend.cart_models import (
    AddToCartRequest,
    Cart,
    CheckoutRequest,
    Order,
    SetQuantityRequest,
)
from backend.dependencies import ConnectionScope, get_cart_store, get_connection_scope

router = APIRouter()

SESSION_QUERY = Query(
    min_length=1, description="Identificador de la sesión dueña del carrito."
)
PRODUCT_PATH = Path(description="Identificador del producto, por ejemplo 'MN-MON-0001'.")


@router.get("/cart", response_model=Cart, summary="Devuelve el carrito de una sesión")
def read_cart(
    session_id: str = SESSION_QUERY,
    connection_scope: ConnectionScope = Depends(get_connection_scope),
    store: carts.CartStore = Depends(get_cart_store),
) -> Cart:
    """Arma el carrito con los precios y el stock que tiene el catálogo ahora.

    Es también el resumen que el usuario confirma antes de comprar (RF-12): el
    total que devuelve acá es el que se cobra en el checkout.
    """
    with connection_scope() as connection:
        return cart.view(connection, store, session_id)


@router.post(
    "/cart/items",
    response_model=Cart,
    summary="Agrega un producto al carrito",
    responses={
        404: {"description": "El producto no existe en el catálogo."},
        409: {"description": "No hay stock suficiente o el producto no se puede comprar."},
        422: {"description": "La cantidad no es un entero mayor a 0."},
    },
)
def add_cart_item(
    request: AddToCartRequest,
    connection_scope: ConnectionScope = Depends(get_connection_scope),
    store: carts.CartStore = Depends(get_cart_store),
) -> Cart:
    """Suma unidades de un producto al carrito, validando el stock (RF-09, RF-10)."""
    with connection_scope() as connection:
        return cart.add_item(
            connection, store, request.session_id, request.product_id, request.quantity
        )


@router.put(
    "/cart/items/{product_id}",
    response_model=Cart,
    summary="Cambia la cantidad de un producto del carrito",
    responses={
        404: {"description": "El producto no existe o no está en el carrito."},
        409: {"description": "No hay stock suficiente."},
        422: {"description": "La cantidad no es un entero mayor a 0."},
    },
)
def set_cart_item(
    request: SetQuantityRequest,
    product_id: str = PRODUCT_PATH,
    connection_scope: ConnectionScope = Depends(get_connection_scope),
    store: carts.CartStore = Depends(get_cart_store),
) -> Cart:
    """Deja la línea en una cantidad exacta, validando el stock (RF-09, RF-10)."""
    with connection_scope() as connection:
        return cart.set_quantity(
            connection, store, request.session_id, product_id, request.quantity
        )


@router.delete(
    "/cart/items/{product_id}",
    response_model=Cart,
    summary="Saca un producto del carrito",
    responses={404: {"description": "El producto no está en el carrito."}},
)
def delete_cart_item(
    product_id: str = PRODUCT_PATH,
    session_id: str = SESSION_QUERY,
    connection_scope: ConnectionScope = Depends(get_connection_scope),
    store: carts.CartStore = Depends(get_cart_store),
) -> Cart:
    """Quita la línea entera de un producto (RF-09)."""
    with connection_scope() as connection:
        return cart.remove_item(connection, store, session_id, product_id)


@router.post(
    "/checkout",
    response_model=Order,
    status_code=201,
    summary="Confirma la compra y crea la orden",
    responses={
        409: {"description": "El carrito está vacío o algún producto se quedó sin stock."},
        422: {"description": "Faltan los datos de envío o la confirmación explícita."},
    },
)
def post_checkout(
    request: CheckoutRequest,
    connection_scope: ConnectionScope = Depends(get_connection_scope),
    store: carts.CartStore = Depends(get_cart_store),
) -> Order:
    """Crea la orden del carrito confirmado (RF-11 a RF-15).

    Pide nombre y dirección de envío, y `confirmed: true`: sin esa
    confirmación explícita el pedido no es válido y no se crea nada. No hay
    pasarela de pago ni datos de tarjeta.

    Al confirmar se descuenta el stock de la base y se vacía el carrito, todo
    en la misma transacción que escribe la orden.
    """
    with connection_scope() as connection:
        return orders.checkout(
            connection,
            store,
            request.session_id,
            customer_name=request.customer_name,
            shipping_address=request.shipping_address,
        )


@router.get(
    "/orders", response_model=list[Order], summary="Lista las órdenes de una sesión"
)
def read_orders(
    session_id: str = SESSION_QUERY,
    connection_scope: ConnectionScope = Depends(get_connection_scope),
) -> list[Order]:
    """Devuelve el historial de órdenes de una sesión, la más nueva primero (RF-16)."""
    with connection_scope() as connection:
        return orders.list_orders(connection, session_id)


@router.get(
    "/orders/{order_id}",
    response_model=Order,
    summary="Trae una orden por su identificador",
    responses={404: {"description": "No existe una orden con ese identificador."}},
)
def read_order(
    order_id: str = Path(description="Identificador de la orden, por ejemplo 'MN-ORD-...'."),
    connection_scope: ConnectionScope = Depends(get_connection_scope),
) -> Order:
    """Devuelve una orden con sus líneas y sus precios congelados (RF-14)."""
    with connection_scope() as connection:
        return orders.get_order(connection, order_id)
