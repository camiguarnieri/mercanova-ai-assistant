"""Las cinco funciones que el LLM puede invocar, sobre `catalog.py`.

Cada herramienta devuelve datos reales de la base o dice explícitamente que no
encontró nada. Ninguna completa un valor por defecto ni adivina: si el dato no
está, la respuesta lo dice y el modelo tiene que decírselo al usuario.

Regla única del stock: la **única** herramienta que devuelve una cantidad de
unidades es `check_availability`. Todas las demás devuelven `in_stock`
booleano, así un número de stock no puede salir de un resultado viejo.

Los valores que el modelo tiene que leer viajan ya escritos como texto, con el
mismo formato que imprime la pantalla: eso es `catalog_text.py`. Una
especificación sale "0 h" y no `{"value_number": 0}`, y un campo de usos vacío
sale "el catálogo no lo aclara" y no `null`. Los dos huecos los completaba el
modelo por su cuenta.

Los mensajes de error están escritos para que el modelo se corrija en el paso
siguiente: empiezan por qué hacer y después aclaran qué pasó. Un mensaje que
solo describe la restricción el modelo lo repite al usuario tal cual.

La validación de los argumentos y el ruteo por nombre están en
`tool_router.py`; acá cada función se invoca con sus parámetros ya válidos.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend import catalog, catalog_text, search_filters

# Cuántos productos devuelve una búsqueda si el modelo no pide otra cosa.
DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 20

MIN_COMPARE = 2
# Tres productos es lo que se puede leer enfrentado, y lo que entra en el
# contexto sin que la respuesta se vaya de tiempo en CPU: con cinco el
# resultado pasa de ~945 a ~1437 tokens. Si el modelo manda más, la herramienta
# recorta y lo aclara en el resultado: un rechazo lo obliga a corregirse, y
# cuando no puede termina pidiéndole al usuario que elija identificadores.
MAX_COMPARE = 3


class ToolError(RuntimeError):
    """Error de la capa de herramientas."""


class UnknownToolError(ToolError):
    """El modelo pidió una herramienta que no existe."""


class ToolArgumentError(ToolError):
    """Los argumentos con los que el modelo invocó la herramienta no sirven."""


# Busca productos con los filtros que armó el modelo.
def search_products(
    connection: sqlite3.Connection,
    category: str | None = None,
    brand: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    recommended_for: str | None = None,
    search: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict[str, Any]:
    """Busca productos en el catálogo.

    De cada producto devuelve un resumen recortado: identificador, nombre,
    marca, categoría, precio, si hay stock y para qué sirve y para qué no. Nada
    de sku, imagen, etiquetas ni descripción larga.

    El stock viene como booleano `in_stock` y no como cantidad. Es una garantía
    de código para el RF-07: si el listado trajera el número, el modelo lo
    repetiría turnos después como si lo hubiera consultado de nuevo. Una
    cantidad solo puede salir de `check_availability`.

    El recorte es a propósito, y es la diferencia entre los dos consumidores
    del catálogo: el frontend usa la API, que devuelve la ficha entera porque
    la muestra en pantalla; el modelo usa esta herramienta, y todo lo que ella
    devuelve él lo tiene que leer dentro de la ventana de contexto que
    configura `OLLAMA_NUM_CTX` (8192 tokens por defecto), corriendo en CPU. Un
    campo que no le sirve para decidir ni para explicar es tiempo de respuesta
    que el usuario espera de más. Si necesita la ficha completa de un producto
    concreto, la pide con `get_product_details`.

    Args:
        connection: Conexión abierta con `db.connect()`.
        category: Categoría exacta, en inglés.
        brand: Nombre o identificador de la marca.
        min_price: Precio vigente mínimo, inclusive.
        max_price: Precio vigente máximo, inclusive.
        recommended_for: Caso de uso, en inglés.
        search: Texto libre, en inglés.
        limit: Cuántos productos devolver. Por defecto `DEFAULT_SEARCH_LIMIT`,
            y se acota a `MAX_SEARCH_LIMIT`.

    Returns:
        Los productos encontrados y el total sin recortar. Si no hay ninguno,
        `found` es `False` y el mensaje lo aclara.
    """
    filters = {
        "category": category,
        "brand": brand,
        "min_price": min_price,
        "max_price": max_price,
        "recommended_for": recommended_for,
        "search": search,
    }

    # Primero se revisan los filtros contra el vocabulario: si están mal, el
    # modelo se entera de todo junto y no después de una búsqueda vacía.
    problems = search_filters.filter_error(
        connection,
        category=category,
        recommended_for=recommended_for,
        min_price=min_price,
        max_price=max_price,
    )
    if problems:
        raise ToolArgumentError(problems)

    page = catalog.list_products_for_assistant(
        connection,
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        recommended_for=recommended_for,
        search=search,
        limit=max(1, min(int(limit), MAX_SEARCH_LIMIT)),
    )
    if not page.items:
        return search_filters.empty_result(connection, filters)
    return {
        "found": True,
        "total": page.total,
        "returned": len(page.items),
        "products": [
            catalog_text.with_uses_text(item.model_dump(mode="json")) for item in page.items
        ],
    }


# Trae la ficha completa de un producto.
def get_product_details(connection: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    """Busca un producto por su identificador.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto.

    La ficha trae todo menos la cantidad de stock: eso es `in_stock`. La ficha
    se pide para leer especificaciones, descripción y garantía, que no cambian
    de un turno al otro; la cantidad sí cambia, y si viniera acá el modelo la
    repetiría sin volver a consultarla. Para afirmar un número está
    `check_availability`.

    Cada especificación viaja en un solo campo `value`, ya escrito con su
    unidad por `catalog_text`: "0 h" y no `{"value_number": 0, "unit": "h"}`.

    Returns:
        La ficha completa del producto, con `in_stock` en lugar de la cantidad
        y las especificaciones escritas como texto.

    Raises:
        catalog.ProductNotFoundError: Si el producto no existe. `run_tool` la
            traduce a un resultado con `error` para que lo lea el modelo.
    """
    detail = catalog.get_product(connection, product_id)
    product = catalog_text.with_uses_text(without_quantity(detail.model_dump(mode="json")))
    product["specifications"] = catalog_text.specifications_text(detail.specifications)
    return {"found": True, "product": product}


# Cambia la cantidad de stock por si hay o no, para todo lo que no sea
# check_availability.
def without_quantity(product: dict[str, Any]) -> dict[str, Any]:
    """Reemplaza `available_qty` por `in_stock` en lo que lee el modelo.

    Regla única: la única herramienta que devuelve una cantidad de stock es
    `check_availability`, que la consulta en el momento en que se pregunta.
    Cualquier otra que traiga el número lo convierte en un dato viejo que el
    modelo repite turnos después como si lo hubiera consultado de nuevo, y eso
    es exactamente lo que el RF-07 no permite.

    Args:
        product: El producto como lo devuelve el modelo Pydantic.

    Returns:
        El mismo producto sin `available_qty` y con `in_stock`. Si no traía la
        cantidad, vuelve igual.
    """
    if "available_qty" not in product:
        return product
    fields = {key: value for key, value in product.items() if key != "available_qty"}
    fields["in_stock"] = product["available_qty"] > 0
    return fields


# Escribe el stock atado a su producto y con la concordancia correcta.
def stock_message(name: str, available: int) -> str:
    """Arma el mensaje del stock para que el modelo lo lea bien escrito.

    El número va con el nombre del producto adelante. Sin el nombre, el modelo
    le puso "7 unidades disponibles" a dos productos a la vez: el 7 era de uno
    y la frase del turno anterior no decía de cuál. Es el mismo mecanismo que
    arregló las especificaciones cruzadas en `compare_products`, atar el dato a
    su dueño.

    El modelo repite este texto casi literal, así que si dice "1 unidades" el
    usuario lee "1 unidades".

    Args:
        name: Nombre comercial del producto al que pertenece la cantidad.
        available: Unidades disponibles, sumando los depósitos.

    Returns:
        La frase con el nombre adelante y la concordancia que corresponde.
    """
    if available == 0:
        return f"{name}: no hay stock disponible en ningún depósito."
    if available == 1:
        return f"{name}: hay 1 unidad disponible."
    return f"{name}: hay {available} unidades disponibles."


# Consulta el stock actual del producto, sumando los depósitos.
def check_availability(connection: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    """Consulta la disponibilidad de un producto.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto.

    Returns:
        Las unidades disponibles y si hay stock. No estima: el número sale de
        sumar el inventario de los depósitos en este momento.

    Raises:
        catalog.ProductNotFoundError: Si el producto no existe.
    """
    detail = catalog.get_product(connection, product_id)
    available = detail.available_qty
    return {
        "found": True,
        "product_id": detail.product_id,
        "name": detail.name,
        "available_qty": available,
        "in_stock": available > 0,
        "active": detail.active,
        "message": stock_message(detail.name, available),
    }


# Enfrenta los datos de dos o tres productos.
def compare_products(
    connection: sqlite3.Connection, product_ids: list[str]
) -> dict[str, Any]:
    """Compara productos entre sí.

    Si llegan más de `MAX_COMPARE` identificadores, compara los primeros y lo
    aclara en el resultado en vez de fallar. Es la diferencia entre un error
    que el modelo tiene que remontar y un resultado que puede usar: cuando no
    podía remontarlo, terminaba pidiéndole al usuario que eligiera
    identificadores, que son internos y el usuario no ve.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_ids: Identificadores de producto. Se usan los primeros
            `MAX_COMPARE`.

    El valor de cada especificación viaja ya escrito con su unidad, igual que
    lo imprime la tabla: "0 h", "40 h", "5.3". Con el número suelto el modelo
    leyó un 0 como que el producto no tenía el dato. Cada valor viaja además con
    el nombre del producto al lado de su `product_id`, porque el modelo escribe
    la prosa con el nombre y al traducir el identificador cambió valores de un
    producto a otro.

    Returns:
        Los datos comparables de cada producto y las especificaciones que
        tienen en común, con el valor de cada uno escrito como texto y con el
        nombre del producto al que pertenece. Si se recortó, trae además
        `compared`, `left_out` y un `note` que lo explica.

    Raises:
        ToolArgumentError: Si no llegan al menos `MIN_COMPARE` identificadores.
        catalog.ProductNotFoundError: Si alguno no existe.
    """
    if not isinstance(product_ids, list) or len(product_ids) < MIN_COMPARE:
        cuantos = len(product_ids) if isinstance(product_ids, list) else 0
        raise ToolArgumentError(
            f"Volvé a invocar compare_products con al menos {MIN_COMPARE} product_id en "
            f"product_ids; esta vez llegaron {cuantos}. Los elegís vos de los resultados "
            f"anteriores: son internos y no se le preguntan al usuario."
        )

    wanted = list(product_ids)
    product_ids = wanted[:MAX_COMPARE]
    left_out = wanted[MAX_COMPARE:]

    details = [catalog.get_product(connection, product_id) for product_id in product_ids]
    products = [
        {
            "product_id": detail.product_id,
            "name": detail.name,
            "brand": detail.brand,
            "category": detail.category,
            "subcategory": detail.subcategory,
            "currency": detail.currency,
            "current_price": detail.current_price,
            # Sin la cantidad y como texto: el número solo lo da
            # check_availability, y con un booleano acá el modelo escribió
            # "1 unidad disponible" para un producto con 29.
            "in_stock": catalog_text.stock_text(detail.available_qty > 0),
            "rating": detail.rating,
            "warranty_months": detail.warranty_months,
            # Escritos como texto: el campo vacío lo completaba con el de otro.
            "recommended_for": catalog_text.uses_text(detail.recommended_for),
            "not_recommended_for": catalog_text.uses_text(detail.not_recommended_for),
        }
        for detail in details
    ]

    # Solo se comparan los atributos que tienen todos, para no enfrentar huecos.
    by_product = [
        {
            (specification.attribute_group, specification.attribute_name): specification
            for specification in detail.specifications
        }
        for detail in details
    ]
    shared = set(by_product[0])
    for attributes in by_product[1:]:
        shared &= set(attributes)

    specifications = [
        {
            "attribute_group": group,
            "attribute_name": name,
            # Cada celda es el texto que imprime la tabla, no el valor crudo, y
            # viaja con el nombre del producto además de su product_id: el
            # modelo escribe la prosa con el nombre, así no tiene que traducir
            # el identificador, y los valores que compiten quedan separados.
            "values": {
                detail.product_id: {
                    "name": detail.name,
                    "value": catalog_text.specification_text(
                        attributes[(group, name)].value_text,
                        attributes[(group, name)].value_number,
                        attributes[(group, name)].unit,
                    ),
                }
                for detail, attributes in zip(details, by_product)
            },
        }
        for group, name in sorted(shared)
    ]
    result = {"found": True, "products": products, "shared_specifications": specifications}
    if left_out:
        # Se dice qué quedó afuera para que el modelo no afirme que comparó
        # todo, y para que pueda volver a invocar con los que faltan.
        result["compared"] = product_ids
        result["left_out"] = left_out
        result["note"] = (
            f"Llegaron {len(wanted)} product_id y compare_products compara hasta "
            f"{MAX_COMPARE}: se compararon {', '.join(product_ids)} y quedaron afuera "
            f"{', '.join(left_out)}. Contestá con estos tres; si el usuario pregunta por "
            f"los otros, volvé a invocar con ellos."
        )
    return result


# Trae los productos que el catálogo relaciona con uno dado.
def get_related_products(
    connection: sqlite3.Connection, product_id: str, relation_type: str | None = None
) -> dict[str, Any]:
    """Busca alternativas, accesorios o productos que se compran juntos.

    Args:
        connection: Conexión abierta con `db.connect()`.
        product_id: Identificador del producto del que se parte.
        relation_type: Tipo de relación, o `None` para los tres.

    Returns:
        Los relacionados, del más fuerte al más débil. Si el producto existe
        pero no tiene relaciones cargadas, `found` es `False` y lo aclara.
    """
    related = catalog.list_related_products(connection, product_id, relation_type)
    if not related:
        kind = f" del tipo '{relation_type}'" if relation_type else ""
        return {
            "found": False,
            "related": [],
            "message": (
                f"El catálogo no tiene productos relacionados{kind} para '{product_id}'."
            ),
        }
    return {
        "found": True,
        "count": len(related),
        "related": [
            {
                "relation_type": item.relation_type,
                "strength": item.strength,
                "product": catalog_text.with_uses_text(
                    without_quantity(item.product.model_dump(mode="json"))
                ),
            }
            for item in related
        ],
    }




