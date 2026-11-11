"""Aplicación FastAPI: arranque, CORS, endpoints del catálogo y errores.

Cada endpoint delega en `catalog.py`: acá solo se traducen parámetros y errores.
El endpoint del asistente está en `chat_api.py` y se incluye al final.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import (
    cart,
    cart_api,
    catalog,
    chat_api,
    config_report,
    db,
    environment,
    inventory,
    llm,
    orders,
    vocabulary,
)
from backend.dependencies import ConnectionScope, get_connection_scope
from backend.models import Brand, Category, ProductDetail, ProductPage

logger = logging.getLogger(__name__)

# El .env se carga al importar este módulo y no en el lifespan a propósito: los
# orígenes de CORS se resuelven más abajo, cuando se arma el middleware, que es
# al importar. Cargándolo en el lifespan, FRONTEND_ORIGINS del archivo llegaría
# tarde y el middleware quedaría armado con los orígenes de desarrollo.
#
# Está acá y no en `backend/__init__.py` para que importar un módulo de
# `backend` no tenga efectos sobre el entorno del proceso: los tests importan
# estos módulos sueltos y no tienen por qué heredar el .env de cada máquina.
environment.load_env_file()

# Origen del frontend de Vite en desarrollo.
DEFAULT_FRONTEND_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


# Deja el modelo cargado, sin que un Ollama apagado tire la API.
def preload_assistant() -> None:
    """Precarga el modelo del asistente y avisa si no se pudo.

    Cargar el modelo tarda unos segundos y, sin esto, esa espera la paga el
    primer mensaje del usuario. Pero el catálogo no necesita Ollama: si no está
    disponible se registra una advertencia y la API arranca igual. El error se
    devuelve recién al usar el chat, que es lo único que lo necesita.
    """
    try:
        llm.preload_model()
    except llm.LLMError as error:
        logger.warning("El asistente va a arrancar en frío: %s", error)


# Arma el esquema de las herramientas con los valores que hay en la base.
def preload_vocabulary() -> None:
    """Deja armado el vocabulario del catálogo y avisa si no se pudo.

    Las categorías y los casos de uso válidos viajan en el esquema que recibe
    el modelo, y salen de la base. Si todavía no está cargada se registra una
    advertencia y se vuelve a intentar en el primer mensaje: el catálogo no
    necesita esto para andar.
    """
    try:
        with db.connection_scope() as connection:
            vocabulary.VOCABULARY.schemas(connection)
    except (db.DatabaseError, sqlite3.Error) as error:
        logger.warning(
            "El asistente va a arrancar sin los valores válidos del catálogo. "
            "Si la base no está cargada, corré: python scripts/load_dataset.py. "
            "Detalle: %s",
            error,
        )


# Deja creadas las tablas que la aplicación escribe, sin tocar las cargadas.
def ensure_schema() -> None:
    """Aplica el esquema sobre la base configurada y avisa si no se pudo.

    `schema.sql` es idempotente —todo es `IF NOT EXISTS`—, así que esto no
    toca ni borra el catálogo ya cargado. Está para las bases que se cargaron
    antes de que existieran `orders` y `order_items`: sin esto, el primer
    checkout fallaría con un error de SQLite en vez de funcionar.

    Si la base no se puede abrir se registra una advertencia y la API arranca
    igual, como con las otras precargas.
    """
    try:
        with db.connection_scope() as connection:
            db.create_schema(connection)
    except (db.DatabaseError, sqlite3.Error) as error:
        logger.warning(
            "No se pudo verificar el esquema de la base. Si todavía no está cargada, "
            "corré: python scripts/load_dataset.py. Detalle: %s",
            error,
        )


# Deja el log de la aplicación en INFO, que es donde sale la configuración.
def configure_logging() -> None:
    """Prepara el logging para que las líneas de `backend` salgan en pantalla.

    Uvicorn configura sus propios loggers y no el raíz, así que sin esto un
    `logger.info()` de un módulo de `backend` no se imprime en ningún lado y el
    reporte de configuración no se vería. Los loggers de uvicorn tienen
    `propagate: false`, así que esto no le duplica las líneas.

    `basicConfig` no hace nada si el logger raíz ya tiene handlers, así que no
    pisa una configuración que haya armado quien levanta la aplicación.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    # Con el raíz en INFO, httpx imprime una línea por cada pedido a Ollama: son
    # varias por turno y tapan el log de la aplicación. Se dejan en WARNING, que
    # es donde avisa lo que sí importa.
    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Corre las precargas del asistente cuando arranca la aplicación.

    La configuración se loguea **primero**: cargar el modelo tarda unos
    segundos y puede fallar, y en los dos casos conviene haber visto ya con qué
    valores está corriendo la aplicación.
    """
    configure_logging()
    config_report.log_configuration(logger, frontend_origins=allowed_origins())
    ensure_schema()
    preload_assistant()
    preload_vocabulary()
    yield


app = FastAPI(
    title="MercaNova",
    description="Catálogo de productos y asistente de compras.",
    version="0.1.0",
    lifespan=lifespan,
)


# Devuelve los orígenes que el navegador tiene permitido usar.
def allowed_origins() -> list[str]:
    """Resuelve los orígenes habilitados para CORS.

    Returns:
        Los orígenes de `FRONTEND_ORIGINS`, separados por coma, o los de
        desarrollo si la variable está vacía o no tiene ningún origen válido.
        Nunca devuelve una lista vacía: eso bloquearía todos los pedidos del
        navegador sin dejar rastro de por qué.
    """
    configured = os.getenv("FRONTEND_ORIGINS") or ""
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if origins:
        return origins
    return [origin.strip() for origin in DEFAULT_FRONTEND_ORIGINS.split(",")]


# Sin esto el navegador bloquea los pedidos del frontend. El catálogo se lee
# con GET, el chat y el checkout mandan con POST, y el carrito cambia una
# cantidad con PUT y saca un producto con DELETE; no se mandan credenciales.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# Un producto inexistente es un 404, no un error del servidor.
@app.exception_handler(catalog.ProductNotFoundError)
def handle_product_not_found(
    request: Request, error: catalog.ProductNotFoundError
) -> JSONResponse:
    """Traduce `ProductNotFoundError` a un 404 con el mensaje de la excepción."""
    return JSONResponse(status_code=404, content={"detail": str(error)})


# Un filtro mal armado es culpa del pedido, no del catálogo.
@app.exception_handler(catalog.InvalidFilterError)
def handle_invalid_filter(request: Request, error: catalog.InvalidFilterError) -> JSONResponse:
    """Traduce `InvalidFilterError` a un 422 con el mensaje de la excepción."""
    return JSONResponse(status_code=422, content={"detail": str(error)})


# Una cantidad que no es un entero mayor a 0 es un pedido mal armado (RF-17).
@app.exception_handler(cart.InvalidQuantityError)
def handle_invalid_quantity(request: Request, error: cart.InvalidQuantityError) -> JSONResponse:
    """Traduce `InvalidQuantityError` a un 422 con el mensaje de la excepción."""
    return JSONResponse(status_code=422, content={"detail": str(error)})


# Tocar una línea que no está en el carrito es un 404, como un producto que no existe.
@app.exception_handler(cart.ProductNotInCartError)
def handle_product_not_in_cart(
    request: Request, error: cart.ProductNotInCartError
) -> JSONResponse:
    """Traduce `ProductNotInCartError` a un 404 con el mensaje de la excepción."""
    return JSONResponse(status_code=404, content={"detail": str(error)})


# Una orden inexistente es un 404.
@app.exception_handler(orders.OrderNotFoundError)
def handle_order_not_found(request: Request, error: orders.OrderNotFoundError) -> JSONResponse:
    """Traduce `OrderNotFoundError` a un 404 con el mensaje de la excepción."""
    return JSONResponse(status_code=404, content={"detail": str(error)})


# Sin stock, carrito vacío o monedas mezcladas: el pedido es válido pero el
# estado del sistema no lo permite ahora. Eso es un 409, no un 500.
@app.exception_handler(cart.CartError)
@app.exception_handler(orders.OrderError)
@app.exception_handler(inventory.StockWriteError)
def handle_cart_conflict(request: Request, error: Exception) -> JSONResponse:
    """Traduce los conflictos del carrito y del checkout a un 409 accionable."""
    return JSONResponse(status_code=409, content={"detail": str(error)})


# Si la base no está cargada, se dice cómo cargarla en vez de fallar seco.
@app.exception_handler(db.DatabaseError)
def handle_database_error(request: Request, error: db.DatabaseError) -> JSONResponse:
    """Traduce los errores de la base a un 503 accionable."""
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.exception_handler(sqlite3.Error)
def handle_sqlite_error(request: Request, error: sqlite3.Error) -> JSONResponse:
    """Traduce un error de SQLite a un 503 que explica cómo cargar la base."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                f"No se pudo consultar el catálogo. Si la base todavía no está cargada, "
                f"corré: python scripts/load_dataset.py. Detalle: {error}"
            )
        },
    )


# Última red: lo que no previmos sale como JSON, no como texto plano.
@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Traduce cualquier error no previsto a un 500 con la forma del resto de la API.

    Starlette solo llega acá cuando ningún handler específico se hizo cargo: la
    búsqueda recorre el MRO de la excepción, así que los de arriba —404, 422,
    409, 503— siguen ganando sobre este. Esto cubre lo que queda afuera, como
    un `httpx.ReadTimeout`, que no es `OSError` y por eso `llm.py` no lo
    traduce.

    Sin esto el usuario recibe el `Internal Server Error` en texto plano que
    escribe Starlette, sin `detail`: el frontend lee `detail` para mostrar qué
    pasó y se queda sin nada que mostrar.

    El mensaje real de la excepción **no viaja al cliente**: puede traer rutas,
    SQL o datos internos. Va al log del servidor, con su traceback, que es
    donde el equipo lo puede leer.
    """
    logger.exception(
        "Error no previsto atendiendo %s %s", request.method, request.url.path, exc_info=error
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "Ocurrió un error inesperado en el servidor y el pedido no se pudo "
                "completar. Volvé a intentar; si sigue pasando, avisale al equipo con "
                "la hora en que pasó: el detalle quedó registrado en el log del servidor."
            )
        },
    )


@app.get("/products", response_model=ProductPage, summary="Lista productos del catálogo")
def read_products(
    category: str | None = Query(default=None, description="Nombre de la categoría."),
    subcategory: str | None = Query(default=None, description="Nombre de la subcategoría."),
    brand: str | None = Query(default=None, description="Nombre o identificador de la marca."),
    recommended_for: str | None = Query(
        default=None,
        description="Uso para el que se recomienda el producto, por ejemplo 'office work'.",
    ),
    min_price: float | None = Query(default=None, description="Precio vigente mínimo."),
    max_price: float | None = Query(default=None, description="Precio vigente máximo."),
    search: str | None = Query(
        default=None,
        description=(
            "Texto libre a buscar en el nombre, las descripciones, recommended_for y tags."
        ),
    ),
    only_active: bool = Query(
        default=True, description="Si es true, no devuelve los productos dados de baja."
    ),
    limit: int = Query(
        default=catalog.DEFAULT_LIMIT,
        ge=1,
        le=catalog.MAX_LIMIT,
        description="Cantidad máxima de productos por página.",
    ),
    offset: int = Query(default=0, ge=0, description="Cantidad de productos a saltear."),
    connection_scope: ConnectionScope = Depends(get_connection_scope),
) -> ProductPage:
    """Busca productos con filtros opcionales y paginado."""
    with connection_scope() as connection:
        return catalog.list_products(
            connection,
            category=category,
            subcategory=subcategory,
            brand=brand,
            recommended_for=recommended_for,
            min_price=min_price,
            max_price=max_price,
            search=search,
            only_active=only_active,
            limit=limit,
            offset=offset,
        )


@app.get(
    "/products/{product_id}",
    response_model=ProductDetail,
    summary="Trae la ficha completa de un producto",
    responses={404: {"description": "El producto no existe en el catálogo."}},
)
def read_product(
    product_id: str = Path(description="Identificador del producto, por ejemplo 'MN-MON-0001'."),
    connection_scope: ConnectionScope = Depends(get_connection_scope),
) -> ProductDetail:
    """Devuelve un producto con su precio, su stock total y sus especificaciones."""
    with connection_scope() as connection:
        return catalog.get_product(connection, product_id)


@app.get("/categories", response_model=list[Category], summary="Lista las categorías")
def read_categories(
    connection_scope: ConnectionScope = Depends(get_connection_scope),
) -> list[Category]:
    """Devuelve los pares categoría/subcategoría del catálogo."""
    with connection_scope() as connection:
        return catalog.list_categories(connection)


@app.get("/brands", response_model=list[Brand], summary="Lista las marcas")
def read_brands(
    connection_scope: ConnectionScope = Depends(get_connection_scope),
) -> list[Brand]:
    """Devuelve las marcas del catálogo."""
    with connection_scope() as connection:
        return catalog.list_brands(connection)


# Se incluyen al final para que los routers hereden los handlers de arriba.
app.include_router(chat_api.router)
app.include_router(cart_api.router)
