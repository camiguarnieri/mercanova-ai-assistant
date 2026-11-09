"""De dónde salió cada product_id que el modelo manda a una herramienta.

El prompt le prohíbe inventar identificadores y no alcanza: un modelo chico
arma 'MN-DOK-0001' por analogía y después le dice al usuario que el producto no
está en el catálogo, que es falso. Acá la regla deja de ser una instrucción y
pasa a ser una condición para ejecutar la herramienta.

La regla es de **procedencia**, no de existencia: un identificador que no
apareció en un resultado de esta conversación no se usa, exista o no en la base.
Si se aceptara porque existe, el modelo seguiría adivinando y acertando a veces,
que es justo lo que no se puede defender.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.tools import ToolArgumentError

__all__ = ["ID_PARAMETERS", "requested_ids", "collect_ids", "check_ids"]

# Los parámetros con los que una herramienta recibe identificadores.
ID_PARAMETERS = ("product_id", "product_ids")

# La clave con la que todos los resultados nombran un producto.
ID_KEY = "product_id"


# Saca los identificadores que el modelo mandó en una invocación.
def requested_ids(arguments: dict[str, Any]) -> list[str]:
    """Lista los product_id que vienen en los argumentos de una herramienta.

    Args:
        arguments: Argumentos ya validados de la invocación.

    Returns:
        Los identificadores pedidos, en el orden en que llegaron y sin
        repetir, vengan de `product_id` o de `product_ids`.
    """
    found: list[str] = []
    for parameter in ID_PARAMETERS:
        value = arguments.get(parameter)
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, (list, tuple)):
            found.extend(item for item in value if isinstance(item, str))
    return list(dict.fromkeys(identifier.strip() for identifier in found if identifier.strip()))


# Recorre el resultado de una herramienta y junta los product_id que trae.
def collect_ids(result: Any) -> set[str]:
    """Busca todos los product_id que aparecen en un resultado.

    Recorre el resultado completo, sin importar la forma que tenga: los
    identificadores aparecen sueltos en `check_availability`, dentro de una
    lista en `search_products` y anidados en `get_related_products`.

    Args:
        result: Lo que devolvió la herramienta.

    Returns:
        Los identificadores que el modelo acaba de ver.
    """
    found: set[str] = set()
    if isinstance(result, dict):
        for key, value in result.items():
            if key == ID_KEY and isinstance(value, str) and value.strip():
                found.add(value.strip())
            else:
                found |= collect_ids(value)
    elif isinstance(result, (list, tuple)):
        for item in result:
            found |= collect_ids(item)
    return found


# Corta la invocación si algún identificador no salió de esta conversación.
def check_ids(arguments: dict[str, Any], known: Iterable[str]) -> None:
    """Verifica que los product_id de una invocación tengan procedencia.

    Args:
        arguments: Argumentos ya validados de la invocación.
        known: Los identificadores que aparecieron en resultados de
            herramientas de esta conversación.

    Raises:
        ToolArgumentError: Si alguno no está entre los conocidos. El mensaje
            dice qué hacer, y aclara que no importa si el producto existe.
    """
    allowed = {identifier.strip() for identifier in known}
    unknown = [
        identifier for identifier in requested_ids(arguments) if identifier not in allowed
    ]
    if not unknown:
        return

    listed = ", ".join(f"'{identifier}'" for identifier in unknown)
    raise ToolArgumentError(
        f"Buscá el producto por su nombre con search_products y volvé a invocar con el "
        f"product_id que devuelva. El product_id {listed} no salió de ninguna búsqueda "
        f"de esta conversación, así que no se puede usar, exista o no en el catálogo: "
        f"los identificadores no se deducen ni se arman por analogía, y tampoco se le "
        f"preguntan al usuario."
    )
