"""Los valores del catálogo escritos como texto, igual que los imprime la pantalla.

Es la contracara de `frontend/src/format.js`: las mismas reglas, del lado del
servidor, para lo que lee el modelo. La idea es que el resultado de una
herramienta diga **exactamente** lo que dice la tabla o la tarjeta, así el
modelo no tiene nada que interpretar.

Dos casos lo justifican, los dos reportados en corridas anteriores:

- `value_number` en 0 viajaba como un número suelto y el modelo lo leía como
  ausencia de dato ("no tiene especificaciones de batería"). Acá sale "0 h",
  que es lo que imprime la tabla.
- `recommended_for` y `not_recommended_for` vacíos viajaban en `null`, y el
  modelo completaba el hueco con el valor de otro producto. Acá sale "el
  catálogo no lo aclara", que es lo que imprime la tarjeta.
- El `in_stock` de `compare_products` viajaba en `true`/`false` y el modelo
  escribió "Stock: 1 unidad disponible" para un producto con 29: tenía un
  booleano y elaboró un número. Acá sale "Con stock" / "Sin stock", que es lo
  que imprime la tarjeta, y no queda nada que elaborar.

Lo que se formatea acá no lleva el valor crudo al lado a propósito: un número
suelto conviviendo con su texto es el número que el modelo puede volver a
malinterpretar.
"""

from __future__ import annotations

from typing import Any

from backend.models import Specification

__all__ = [
    "IN_STOCK",
    "MISSING_SPECIFICATION",
    "MISSING_USES",
    "NO_FEATURE",
    "OUT_OF_STOCK",
    "USE_CASE_FIELDS",
    "number_text",
    "specification_text",
    "specifications_text",
    "stock_text",
    "uses_text",
    "with_uses_text",
]

# Lo que se dice cuando el catálogo no tiene cargado el valor de un atributo.
MISSING_SPECIFICATION = "el catálogo no trae este dato"

# Lo que se dice cuando el campo de usos viene vacío. Es la misma frase que
# imprime la tarjeta del chat.
MISSING_USES = "el catálogo no lo aclara"

# El texto "None" del catálogo significa que el producto NO tiene esa
# característica, y es distinto de que falte el dato. La pantalla lo imprime
# como "No", así que acá viaja igual.
NO_FEATURE = "No"

# Los campos de usos que se escriben como texto en vez de viajar en null.
USE_CASE_FIELDS = ("recommended_for", "not_recommended_for")

# Lo que se dice del stock cuando no se consultó la cantidad. Son las mismas dos
# frases que imprime la tarjeta del chat.
IN_STOCK = "Con stock"
OUT_OF_STOCK = "Sin stock"


# Escribe un número como lo imprime la pantalla, sin el ".0" de más.
def number_text(value: float) -> str:
    """Convierte un número del catálogo en el texto que muestra la interfaz.

    Args:
        value: El valor numérico del atributo.

    Returns:
        El número sin decimales si es entero ("40", "0") y con ellos si no
        ("5.3"). Es el mismo formato que imprime la tabla de comparación.
    """
    return str(int(value)) if float(value).is_integer() else str(value)


# Escribe el valor de una especificación con su unidad.
def specification_text(
    value_text: str | None, value_number: float | None, unit: str | None
) -> str:
    """Arma el texto de una especificación para que lo lea el modelo.

    Args:
        value_text: Valor de texto del atributo, o `None` si es numérico.
        value_number: Valor numérico del atributo, o `None` si es de texto.
        unit: Unidad del valor numérico, o `None` si no aplica.

    Returns:
        El valor con su unidad ("0 h", "40 h", "5.3"), `NO_FEATURE` si el
        catálogo trae el texto "None", o `MISSING_SPECIFICATION` si no hay
        ningún valor cargado. Nunca devuelve un número solo.
    """
    if value_text is not None:
        return NO_FEATURE if value_text == "None" else value_text
    if value_number is None:
        return MISSING_SPECIFICATION
    written = number_text(value_number)
    return f"{written} {unit}" if unit else written


# Convierte las especificaciones de una ficha en pares atributo/texto.
def specifications_text(specifications: list[Specification]) -> list[dict[str, str]]:
    """Escribe las especificaciones de un producto como texto.

    Args:
        specifications: Las especificaciones tal como las trae el catálogo.

    Returns:
        Una lista con el grupo, el nombre y el valor ya escrito de cada
        atributo. No viaja el número crudo: ver el docstring del módulo.
    """
    return [
        {
            "attribute_group": specification.attribute_group,
            "attribute_name": specification.attribute_name,
            "value": specification_text(
                specification.value_text, specification.value_number, specification.unit
            ),
        }
        for specification in specifications
    ]


# Escribe si hay stock, sin decir cuántas unidades.
def stock_text(in_stock: bool) -> str:
    """Devuelve el estado del stock como lo imprime la tarjeta.

    Un booleano invita a elaborar: con `in_stock` en `true` el modelo escribió
    "Stock: 1 unidad disponible" para un producto con 29 unidades, que nunca
    consultó. Una frase cerrada no deja nada que completar. La cantidad sigue
    saliendo solo de `check_availability`.

    Args:
        in_stock: Si hay unidades disponibles ahora mismo.

    Returns:
        `IN_STOCK` o `OUT_OF_STOCK`.
    """
    return IN_STOCK if in_stock else OUT_OF_STOCK


# Escribe el campo de usos, o aclara que el catálogo no lo trae.
def uses_text(value: str | None) -> str:
    """Devuelve los usos de un producto, o la frase del campo vacío.

    Args:
        value: El contenido de `recommended_for` o `not_recommended_for`.

    Returns:
        El valor tal como está en el catálogo, o `MISSING_USES` si viene
        vacío. Nunca devuelve `None`: el hueco es lo que el modelo completaba
        con el valor de otro producto.
    """
    return value.strip() if value and value.strip() else MISSING_USES


# Reemplaza los campos de usos vacíos de un producto ya serializado.
def with_uses_text(product: dict[str, Any]) -> dict[str, Any]:
    """Escribe los campos de usos de un producto como texto.

    Args:
        product: El producto como lo devuelve `model_dump()`.

    Returns:
        El mismo producto con `recommended_for` y `not_recommended_for`
        escritos. Los campos que no estén en el producto no se agregan.
    """
    written = dict(product)
    for field in USE_CASE_FIELDS:
        if field in written:
            written[field] = uses_text(written[field])
    return written
