"""Modelos Pydantic del carrito y de las órdenes.

Están aparte de `models.py`, que tiene el catálogo, y de `chat_models.py`, que
tiene la conversación: esto es el contrato de la compra.

El carrito guarda **solo product_id y cantidad**. El nombre, el precio y el
stock no se guardan: se vuelven a leer de la base cada vez que se arma esta
vista. Un carrito que guardara el precio mostraría un número viejo, que es el
mismo problema que `tools.without_quantity()` evita con el stock.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.chat_models import MAX_SESSION_ID_LENGTH
from backend.models import MODEL_CONFIG

__all__ = [
    "MAX_NAME_LENGTH",
    "MAX_ADDRESS_LENGTH",
    "CartLine",
    "Cart",
    "OrderLine",
    "Order",
    "AddToCartRequest",
    "SetQuantityRequest",
    "CheckoutRequest",
]

# Topes para que un pedido mal armado no cargue la memoria del servidor.
MAX_NAME_LENGTH = 120
MAX_ADDRESS_LENGTH = 300


class CartLine(BaseModel):
    """Un producto del carrito, con el dato que tiene el catálogo ahora."""

    model_config = MODEL_CONFIG

    product_id: str = Field(description="Identificador del producto, por ejemplo 'MN-MON-0001'.")
    name: str = Field(description="Nombre comercial del producto, como está en el catálogo.")
    brand: str = Field(description="Nombre de la marca del producto.")
    quantity: int = Field(description="Unidades de este producto en el carrito. Siempre mayor a 0.")
    currency: str | None = Field(
        default=None, description="Moneda del precio, por ejemplo 'USD'. Null si no hay precio."
    )
    unit_price: float | None = Field(
        default=None,
        description=(
            "Precio vigente de una unidad, leído del catálogo en este momento. Null "
            "significa que el precio no está cargado: no se estima."
        ),
    )
    line_total: float | None = Field(
        default=None,
        description="Precio por la cantidad, redondeado a dos decimales. Null si no hay precio.",
    )
    available_qty: int = Field(
        description=(
            "Unidades disponibles del producto ahora mismo, sumando los depósitos. Puede "
            "ser menor que quantity si el stock bajó después de agregarlo al carrito."
        )
    )


class Cart(BaseModel):
    """El carrito de una sesión, con el total calculado por el sistema."""

    model_config = MODEL_CONFIG

    session_id: str = Field(description="La sesión a la que pertenece el carrito.")
    items: list[CartLine] = Field(
        default_factory=list,
        description="Los productos del carrito, en el orden en que se agregaron.",
    )
    currency: str | None = Field(
        default=None, description="Moneda del total. Null si el carrito está vacío."
    )
    total: float = Field(
        default=0.0,
        description=(
            "Suma de los line_total, redondeada a dos decimales. Lo calcula el sistema con "
            "los precios del catálogo: el asistente no lo recalcula ni lo estima."
        ),
    )
    item_count: int = Field(
        default=0, description="Cantidad total de unidades en el carrito, sumando las líneas."
    )


class OrderLine(BaseModel):
    """Una línea de una orden, con el precio al momento de la compra."""

    model_config = MODEL_CONFIG

    product_id: str = Field(description="Identificador del producto comprado.")
    name: str = Field(description="Nombre del producto cuando se confirmó la compra.")
    quantity: int = Field(description="Unidades compradas de este producto.")
    unit_price: float = Field(description="Precio de una unidad al momento de confirmar la compra.")
    currency: str = Field(description="Moneda del precio, por ejemplo 'USD'.")
    line_total: float = Field(description="Precio por la cantidad, redondeado a dos decimales.")


class Order(BaseModel):
    """Una orden confirmada (RF-14).

    Es la foto de lo que el usuario confirmó: los precios y los nombres quedan
    como estaban en ese momento, aunque después cambie el catálogo.
    """

    model_config = MODEL_CONFIG

    order_id: str = Field(
        description="Identificador de la orden, por ejemplo 'MN-ORD-20261109-3F2A91C4'."
    )
    session_id: str = Field(description="La sesión desde la que se confirmó la compra.")
    created_at: datetime = Field(description="Momento en que se confirmó la orden, en UTC.")
    customer_name: str = Field(description="Nombre de quien recibe el envío.")
    shipping_address: str = Field(description="Dirección de envío.")
    currency: str = Field(description="Moneda del total de la orden.")
    total_amount: float = Field(description="Total pagado, redondeado a dos decimales.")
    items: list[OrderLine] = Field(
        default_factory=list, description="Las líneas de la orden, con sus precios congelados."
    )


class AddToCartRequest(BaseModel):
    """Lo que manda el frontend para agregar un producto al carrito."""

    model_config = MODEL_CONFIG

    session_id: str = Field(
        min_length=1,
        max_length=MAX_SESSION_ID_LENGTH,
        description="Identificador de la sesión dueña del carrito.",
    )
    product_id: str = Field(
        min_length=1, description="Identificador del producto a agregar, por ejemplo 'MN-MON-0001'."
    )
    quantity: int = Field(
        default=1, description="Unidades a sumar a las que ya haya en el carrito. Mayor a 0."
    )


class SetQuantityRequest(BaseModel):
    """Lo que manda el frontend para fijar la cantidad de una línea."""

    model_config = MODEL_CONFIG

    session_id: str = Field(
        min_length=1,
        max_length=MAX_SESSION_ID_LENGTH,
        description="Identificador de la sesión dueña del carrito.",
    )
    quantity: int = Field(
        description="Cantidad final de la línea, mayor a 0. Para sacarla, se usa DELETE."
    )


class CheckoutRequest(BaseModel):
    """Lo que manda el frontend para confirmar la compra (RF-11, RF-12, RF-13).

    `confirmed` solo acepta `true`: es la confirmación explícita del RF-12
    escrita en el contrato, así ningún cliente puede llegar a la orden sin
    mandarla. El resumen que el usuario confirma es lo que devuelve `GET /cart`.
    """

    model_config = MODEL_CONFIG

    session_id: str = Field(
        min_length=1,
        max_length=MAX_SESSION_ID_LENGTH,
        description="Identificador de la sesión dueña del carrito.",
    )
    customer_name: str = Field(
        min_length=1,
        max_length=MAX_NAME_LENGTH,
        description="Nombre de quien recibe el envío. Es un dato mínimo y es obligatorio.",
    )
    shipping_address: str = Field(
        min_length=1,
        max_length=MAX_ADDRESS_LENGTH,
        description="Dirección de envío. Es un dato mínimo y es obligatorio.",
    )
    confirmed: Literal[True] = Field(
        description=(
            "Tiene que ser true: es la confirmación explícita del resumen del carrito. "
            "Cualquier otro valor hace que el pedido no sea válido y la orden no se cree."
        )
    )
