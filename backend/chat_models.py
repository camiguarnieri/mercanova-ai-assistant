"""Modelos Pydantic del chat: lo que entra y sale del endpoint del asistente.

Están aparte de `models.py`, que tiene los modelos del catálogo: esto es el
contrato de la conversación, no datos de producto.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.models import MODEL_CONFIG

# Topes para que un pedido mal armado no cargue la memoria del servidor.
MAX_SESSION_ID_LENGTH = 100
MAX_MESSAGE_LENGTH = 2000


class ToolInvocation(BaseModel):
    """Una herramienta que el asistente ejecutó para armar su respuesta."""

    model_config = MODEL_CONFIG

    name: str = Field(description="Nombre de la herramienta, por ejemplo 'search_products'.")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Argumentos con los que se ejecutó, ya validados. Vacío si la herramienta "
            "no lleva argumentos, como list_categories."
        ),
    )


class ChatRequest(BaseModel):
    """El mensaje que manda el frontend."""

    # Sin `str_strip_whitespace` el modelo aceptaría un mensaje de solo espacios.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str = Field(
        min_length=1,
        max_length=MAX_SESSION_ID_LENGTH,
        description=(
            "Identificador de la conversación, generado por el cliente. Con el mismo "
            "valor se sigue la conversación anterior; con uno nuevo se empieza de cero."
        ),
    )
    message: str = Field(
        min_length=1,
        max_length=MAX_MESSAGE_LENGTH,
        description="Lo que escribió el usuario, en lenguaje natural.",
    )


class ShownProduct(BaseModel):
    """Un producto que apareció en una búsqueda, para mostrarlo como tarjeta.

    Ignora el resto del resumen a propósito: la tarjeta muestra solo estos
    campos, y lo que no se manda no ocupa lugar en la respuesta.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    product_id: str = Field(description="Identificador del producto.")
    name: str = Field(description="Nombre comercial del producto.")
    brand: str = Field(description="Nombre de la marca.")
    currency: str | None = Field(default=None, description="Moneda del precio.")
    current_price: float | None = Field(
        default=None, description="Precio vigente, o null si el catálogo no lo tiene."
    )
    in_stock: bool = Field(description="True si hay unidades disponibles ahora.")
    recommended_for: str = Field(
        description=(
            "Usos recomendados, separados por punto y coma, o la frase del campo vacío "
            "que escribe `catalog_text`. Nunca viene null: la tarjeta imprime lo mismo "
            "que leyó el modelo."
        )
    )
    not_recommended_for: str = Field(
        description="Usos no recomendados, o la frase del campo vacío."
    )


class ComparedValue(BaseModel):
    """El valor de una especificación para uno de los productos comparados."""

    model_config = MODEL_CONFIG

    name: str = Field(
        description=(
            "Nombre del producto al que pertenece este valor. Viaja al lado del valor "
            "porque la prosa se escribe con el nombre y no con el product_id: al "
            "traducir el identificador, el modelo cambió valores de un producto a otro."
        )
    )
    value: str = Field(
        description=(
            "El valor ya escrito con su unidad ('0 h', '40 h', '5.3'), o la frase del "
            "dato que el catálogo no trae. Nunca es un número suelto."
        )
    )


class ComparedSpecification(BaseModel):
    """Una especificación que tienen todos los productos comparados."""

    model_config = MODEL_CONFIG

    attribute_group: str = Field(description="Grupo del atributo, por ejemplo 'Battery'.")
    attribute_name: str = Field(description="Nombre del atributo, por ejemplo 'Battery Life'.")
    values: dict[str, ComparedValue] = Field(
        description=(
            "El valor de cada producto, indexado por su product_id. Es el mismo texto "
            "que recibió el modelo: lo escribe `catalog_text` una sola vez, así la "
            "tabla y el resultado de la herramienta no pueden decir cosas distintas."
        )
    )


class ComparedProduct(BaseModel):
    """Un producto de una comparación, con lo que necesita el encabezado.

    Ignora el resto del resultado de `compare_products` a propósito: la tabla
    solo necesita identificar la columna, y lo que no se manda no ocupa lugar
    en la respuesta.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    product_id: str = Field(description="Identificador del producto.")
    name: str = Field(description="Nombre comercial, para el encabezado de la columna.")


class Comparison(BaseModel):
    """Una comparación de productos, tal como la devolvió la herramienta.

    Viaja al frontend para que la tabla salga del resultado de
    `compare_products` y no de la prosa del modelo, que ya dio vuelta un valor
    al escribirlo. Mismo criterio que la traza de herramientas: lo que se
    muestra como dato sale del catálogo.
    """

    model_config = MODEL_CONFIG

    products: list[ComparedProduct] = Field(description="Los productos comparados, en orden.")
    specifications: list[ComparedSpecification] = Field(
        default_factory=list,
        description="Las especificaciones que tienen en común, con el valor de cada producto.",
    )


class AssistantTurn(BaseModel):
    """La respuesta del asistente y las herramientas con las que la armó."""

    model_config = MODEL_CONFIG

    reply: str = Field(description="La respuesta del asistente, en español.")
    products: list[ShownProduct] = Field(
        default_factory=list,
        description=(
            "Los productos que devolvieron las búsquedas de este turno, sin repetir, "
            "para que la interfaz los muestre como tarjetas con el dato del catálogo. "
            "El texto del asistente queda al lado como explicación."
        ),
    )
    comparisons: list[Comparison] = Field(
        default_factory=list,
        description=(
            "Las comparaciones que devolvió compare_products en este turno, para que la "
            "interfaz las muestre como tabla desde el dato y no desde el texto."
        ),
    )
    tools_used: list[ToolInvocation] = Field(
        default_factory=list,
        description=(
            "Las herramientas que se ejecutaron en este turno, en orden. Es la "
            "evidencia de que los datos salieron del catálogo y no del modelo. "
            "Vacío si el asistente respondió sin consultar nada, por ejemplo al "
            "repreguntar."
        ),
    )


class ChatResponse(AssistantTurn):
    """El turno del asistente, con la sesión a la que pertenece."""

    model_config = MODEL_CONFIG

    session_id: str = Field(
        description="La sesión en la que quedó guardada la conversación."
    )
