"""Endpoints FastAPI del catálogo.

Cada endpoint delega en `catalog.py`: acá solo se traducen parámetros y errores.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import catalog, db
from backend.models import Brand, Category, ProductDetail, ProductPage

# Origen del frontend de Vite en desarrollo.
DEFAULT_FRONTEND_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

app = FastAPI(
    title="MercaNova",
    description="Catálogo de productos para el asistente de compras.",
    version="0.1.0",
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


# Sin esto el navegador bloquea los pedidos del frontend. El catálogo es de
# solo lectura, así que se habilita únicamente GET y no se mandan credenciales.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# Fábrica de conexiones: se llama adentro del endpoint, no antes.
ConnectionScope = Callable[[], AbstractContextManager[sqlite3.Connection]]


def get_connection_scope() -> ConnectionScope:
    """Entrega la fábrica con la que cada endpoint abre su conexión.

    No devuelve una conexión ya abierta a propósito. FastAPI corre las
    dependencias sincrónicas y los endpoints sincrónicos como tareas separadas
    del threadpool, que pueden caer en hilos distintos; una conexión de SQLite
    creada en la dependencia y usada en el endpoint falla con "SQLite objects
    created in a thread can only be used in that same thread". Devolviendo la
    fábrica, cada endpoint abre y cierra la suya en su propio hilo.

    Returns:
        Un callable que da un context manager con la conexión.
    """
    return db.connection_scope


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
