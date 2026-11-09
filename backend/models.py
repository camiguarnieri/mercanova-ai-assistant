"""Modelos Pydantic de respuesta del catálogo.

Las descripciones de los campos viajan en el JSON Schema que recibe el LLM, así
que están escritas para que las lea él.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

# Configuración común: no se aceptan campos de más y los textos vienen limpios.
MODEL_CONFIG = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Brand(BaseModel):
    """Una marca del catálogo."""

    model_config = MODEL_CONFIG

    brand_id: str = Field(description="Identificador de la marca, por ejemplo 'BR001'.")
    brand_name: str = Field(description="Nombre de la marca, por ejemplo 'NovaTech'.")
    country_of_origin: str | None = Field(
        default=None, description="País de origen de la marca, o null si no está cargado."
    )
    positioning: str | None = Field(
        default=None,
        description="Posicionamiento de la marca según el catálogo: 'premium', 'balanced' u otro.",
    )


class Category(BaseModel):
    """Un par categoría/subcategoría del catálogo."""

    model_config = MODEL_CONFIG

    category_id: str = Field(description="Identificador de la categoría, por ejemplo 'CAT01'.")
    category_name: str = Field(description="Nombre de la categoría, por ejemplo 'Monitors'.")
    subcategory_id: str = Field(
        description="Identificador de la subcategoría, por ejemplo 'SUB001'."
    )
    subcategory_name: str = Field(
        description="Nombre de la subcategoría, por ejemplo 'Office'. Se repite entre categorías."
    )
    department: str | None = Field(
        default=None, description="Departamento al que pertenece la categoría."
    )


class Specification(BaseModel):
    """Una especificación técnica de un producto."""

    model_config = MODEL_CONFIG

    attribute_group: str = Field(
        description="Grupo al que pertenece el atributo, por ejemplo 'Display'."
    )
    attribute_name: str = Field(
        description="Nombre del atributo, por ejemplo 'Screen Size' o 'Water Resistance'."
    )
    value_text: str | None = Field(
        default=None,
        description=(
            "Valor de texto del atributo. Atención: el texto 'None' es un valor real y "
            "significa que el producto NO tiene esa característica. Es distinto de null, "
            "que significa que el valor de este atributo es numérico y está en value_number."
        ),
    )
    value_number: float | None = Field(
        default=None,
        description=(
            "Valor numérico del atributo. Cada especificación trae valor en value_text o en "
            "value_number, nunca en las dos."
        ),
    )
    unit: str | None = Field(
        default=None,
        description="Unidad del valor numérico, por ejemplo 'in' o 'Hz'. Null si no aplica.",
    )


class Product(BaseModel):
    """Resumen de un producto, para listados."""

    model_config = MODEL_CONFIG

    product_id: str = Field(description="Identificador del producto, por ejemplo 'MN-MON-0001'.")
    sku: str = Field(description="Código de artículo del producto.")
    name: str = Field(description="Nombre comercial del producto.")
    brand: str = Field(description="Nombre de la marca del producto.")
    category: str = Field(description="Categoría del producto, por ejemplo 'Monitors'.")
    subcategory: str = Field(description="Subcategoría del producto, por ejemplo 'Gaming'.")
    short_description: str | None = Field(
        default=None, description="Descripción corta del producto, de una línea."
    )
    recommended_for: str | None = Field(
        default=None,
        description=(
            "Usos para los que el catálogo recomienda el producto, separados por punto y coma, "
            "por ejemplo 'office work; programming'. Viene en el resumen para poder justificar "
            "una recomendación sin pedir la ficha completa. Null si el catálogo no lo aclara."
        ),
    )
    currency: str | None = Field(
        default=None, description="Moneda del precio, por ejemplo 'USD'. Null si no hay precio."
    )
    current_price: float | None = Field(
        default=None,
        description=(
            "Precio vigente del producto. Null significa que el precio no está cargado: en ese "
            "caso no hay que estimarlo, hay que decir que no se tiene el dato."
        ),
    )
    available_qty: int = Field(
        description=(
            "Unidades disponibles en total, sumando los 5 depósitos. 0 significa sin stock."
        )
    )
    image_url: str | None = Field(
        default=None, description="URL de la imagen del producto, para mostrar en el listado."
    )
    active: bool = Field(
        description="True si el producto está activo en el catálogo, false si fue dado de baja."
    )


class ProductSummary(BaseModel):
    """Resumen de un producto recortado para el asistente.

    Tiene menos campos que `Product` a propósito: `Product` es lo que muestra el
    frontend, y esto es lo único que necesita el modelo para elegir un producto
    y justificar por qué lo recomienda. Cada campo de más ocupa lugar en su
    ventana de contexto.

    El stock viene como booleano, no como número: un listado que trae la
    cantidad se vuelve un dato viejo en el turno siguiente, y el modelo lo
    repetía sin volver a consultarlo.
    """

    model_config = MODEL_CONFIG

    product_id: str = Field(description="Identificador del producto, por ejemplo 'MN-MON-0001'.")
    name: str = Field(description="Nombre comercial del producto.")
    brand: str = Field(description="Nombre de la marca del producto.")
    category: str = Field(description="Categoría del producto, por ejemplo 'Monitors'.")
    currency: str | None = Field(
        default=None, description="Moneda del precio, por ejemplo 'USD'. Null si no hay precio."
    )
    current_price: float | None = Field(
        default=None,
        description=(
            "Precio vigente del producto. Null significa que el precio no está cargado: en ese "
            "caso no hay que estimarlo, hay que decir que no se tiene el dato."
        ),
    )
    in_stock: bool = Field(
        description=(
            "True si ahora mismo hay unidades disponibles en algún depósito. No dice "
            "cuántas: para afirmar una cantidad hay que consultarla con check_availability, "
            "que la trae del momento en que se pregunta."
        )
    )
    recommended_for: str | None = Field(
        default=None,
        description=(
            "Usos para los que el catálogo recomienda el producto, separados por punto y coma. "
            "Es con lo que se justifica la recomendación. Null si el catálogo no lo aclara."
        ),
    )
    not_recommended_for: str | None = Field(
        default=None,
        description=(
            "Usos para los que el catálogo NO recomienda el producto. Si desaconseja justo lo "
            "que quiere hacer el usuario, hay que avisarle. Null si no aclara."
        ),
    )


class ProductSummaryPage(BaseModel):
    """Los resultados de una búsqueda del asistente."""

    model_config = MODEL_CONFIG

    items: list[ProductSummary] = Field(description="Los productos encontrados.")
    total: int = Field(
        description="Cantidad total de productos que cumplen los filtros, sin recortar."
    )


class ProductDetail(Product):
    """Ficha completa de un producto, con precio, stock y especificaciones."""

    model_config = MODEL_CONFIG

    description: str | None = Field(default=None, description="Descripción larga del producto.")
    not_recommended_for: str | None = Field(
        default=None,
        description="Usos para los que el catálogo NO recomienda el producto. Null si no aclara.",
    )
    key_features: str | None = Field(
        default=None, description="Características principales, separadas por punto y coma."
    )
    tags: str | None = Field(
        default=None,
        description=(
            "Etiquetas del producto separadas por punto y coma, por ejemplo "
            "'monitor; qhd; office-work'. Incluyen los casos de uso y las mira la búsqueda libre."
        ),
    )
    color: str | None = Field(default=None, description="Color del producto.")
    weight_kg: float | None = Field(default=None, description="Peso del producto en kilogramos.")
    warranty_months: int | None = Field(default=None, description="Garantía en meses.")
    return_days: int | None = Field(default=None, description="Días de plazo para devolución.")
    rating: float | None = Field(default=None, description="Puntaje promedio, de 0 a 5.")
    review_count: int | None = Field(default=None, description="Cantidad de reseñas.")
    launch_date: date | None = Field(default=None, description="Fecha de lanzamiento.")
    list_price: float | None = Field(
        default=None, description="Precio de lista, sin el descuento aplicado."
    )
    discount_percent: int | None = Field(
        default=None, description="Descuento vigente en porcentaje, de 0 a 100."
    )
    tax_included: bool | None = Field(
        default=None, description="True si el precio ya incluye impuestos."
    )
    price_updated_at: date | None = Field(
        default=None, description="Fecha de la última actualización del precio."
    )
    specifications: list[Specification] = Field(
        default_factory=list,
        description="Especificaciones técnicas del producto, agrupadas por attribute_group.",
    )


class RelatedProduct(BaseModel):
    """Un producto relacionado con otro, según el catálogo."""

    model_config = MODEL_CONFIG

    relation_type: str = Field(
        description=(
            "Tipo de relación: 'alternative_to' (alternativa al producto consultado), "
            "'accessory_for' (accesorio para ese producto) u 'often_bought_with' "
            "(se suele comprar junto con ese producto)."
        )
    )
    strength: float = Field(
        description="Fuerza de la relación según el catálogo, de 0 a 1. Más alto es más fuerte."
    )
    product: Product = Field(description="El resumen del producto relacionado.")


class ProductPage(BaseModel):
    """Una página de resultados del listado de productos."""

    model_config = MODEL_CONFIG

    items: list[Product] = Field(description="Los productos de esta página.")
    total: int = Field(
        description="Cantidad total de productos que cumplen los filtros, sin paginar."
    )
    limit: int = Field(description="Cantidad máxima de productos que devuelve esta página.")
    offset: int = Field(description="Cantidad de productos salteados antes de esta página.")
    has_more: bool = Field(
        description="True si quedan más productos después de esta página; pedir el siguiente offset."
    )
