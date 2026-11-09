"""Qué parte del resultado de una herramienta ve el modelo.

Las herramientas devuelven el dato del catálogo completo. La interfaz lo usa
entero —la tarjeta y la tabla se imprimen desde ese dato—, y al modelo se le
manda una copia sin los campos de este módulo.

Hoy hay uno solo: `not_recommended_for`. Probamos dárselo en `null` cuando el
catálogo no lo trae y probamos dárselo como la frase "el catálogo no lo
aclara": en las dos formas, el Aether Sound 880 —que lo tiene vacío— terminó
con el "air travel" de los otros cuatro productos de la misma búsqueda. Dos
intentos de que lo lea bien y dos fallas, así que deja de viajar.

El usuario no pierde el dato: la tarjeta lo sigue imprimiendo desde el
resultado completo, y la ficha del producto lo trae de la API. Lo que se pierde
es que el asistente avise por su cuenta cuando el catálogo desaconseja lo que
el usuario quiere hacer; está anotado como trade-off en REVIEW.md.

Es el mismo criterio que `tools.without_quantity()`: si un dato se le cruza al
modelo de un producto a otro, la solución es que no lo tenga, no pedirle en el
prompt que lo use bien.
"""

from __future__ import annotations

from typing import Any

__all__ = ["HIDDEN_FIELDS", "for_the_model"]

# Los campos que no viajan al modelo, a ninguna profundidad del resultado.
HIDDEN_FIELDS = frozenset({"not_recommended_for"})


# Saca de un resultado los campos que el modelo no tiene que recibir.
def for_the_model(result: Any) -> Any:
    """Devuelve una copia del resultado sin los campos ocultos.

    Recorre el resultado entero: los campos se sacan estén donde estén, en el
    producto de una búsqueda, en la ficha, en un producto comparado o dentro de
    un relacionado.

    Args:
        result: Lo que devolvió la herramienta, tal como lo usa la interfaz.

    Returns:
        Una copia lista para serializar al modelo. El original no se toca: lo
        necesita la interfaz completo.
    """
    if isinstance(result, dict):
        return {
            key: for_the_model(value)
            for key, value in result.items()
            if key not in HIDDEN_FIELDS
        }
    if isinstance(result, list):
        return [for_the_model(item) for item in result]
    return result
