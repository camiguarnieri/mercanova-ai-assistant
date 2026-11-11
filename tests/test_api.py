"""Tests de backend/api.py: los endpoints del catálogo con el cliente de test."""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import api, db
from backend.vocabulary import Vocabulary


@pytest.fixture
def client(catalog_database: Path) -> Iterator[TestClient]:
    """Un cliente de test apuntado a la base de prueba, no a la real."""
    api.app.dependency_overrides[api.get_connection_scope] = lambda: partial(
        db.connection_scope, catalog_database
    )
    with TestClient(api.app) as test_client:
        yield test_client
    api.app.dependency_overrides.clear()


def test_the_products_endpoint_answers_with_a_page(client: TestClient) -> None:
    response = client.get("/products")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert body["offset"] == 0
    assert len(body["items"]) == 4


def test_the_products_endpoint_returns_the_expected_shape(client: TestClient) -> None:
    body = client.get("/products", params={"limit": 1}).json()

    assert set(body) == {"items", "total", "limit", "offset", "has_more"}
    assert set(body["items"][0]) == {
        "product_id",
        "sku",
        "name",
        "brand",
        "category",
        "subcategory",
        "short_description",
        "recommended_for",
        "currency",
        "current_price",
        "available_qty",
        "active",
        "image_url",
    }


def test_the_products_endpoint_filters_by_category(client: TestClient) -> None:
    body = client.get("/products", params={"category": "Monitors"}).json()

    assert body["total"] == 2


def test_the_products_endpoint_filters_by_price_range(client: TestClient) -> None:
    body = client.get("/products", params={"min_price": 100, "max_price": 500}).json()

    assert {item["name"] for item in body["items"]} == {"Nova Sound Pro", "Nova Vision 24"}


def test_the_products_endpoint_searches_free_text(client: TestClient) -> None:
    body = client.get("/products", params={"search": "240 Hz"}).json()

    assert [item["name"] for item in body["items"]] == ["Flux Vision 27"]


def test_the_products_endpoint_searches_by_use_case(client: TestClient) -> None:
    # "programming" solo está en recommended_for.
    body = client.get("/products", params={"search": "programming"}).json()

    assert [item["name"] for item in body["items"]] == ["Nova Vision 24"]


def test_the_products_endpoint_searches_the_tags(client: TestClient) -> None:
    body = client.get("/products", params={"search": "noise-cancelling"}).json()

    assert [item["name"] for item in body["items"]] == ["Nova Sound Pro"]


def test_the_products_endpoint_filters_by_recommended_for(client: TestClient) -> None:
    body = client.get("/products", params={"recommended_for": "office work"}).json()

    assert {item["name"] for item in body["items"]} == {"Nova Vision 24", "Nova Sound Pro"}


def test_the_product_endpoint_returns_the_use_case_fields(client: TestClient) -> None:
    body = client.get("/products/MN-MON-0001").json()

    assert body["recommended_for"] == "office work; programming"
    assert body["tags"] == "monitor; display; qhd"


def test_the_listing_brings_recommended_for_to_justify_each_product(
    client: TestClient,
) -> None:
    body = client.get("/products", params={"recommended_for": "office work"}).json()

    # Alcanza con el listado para justificar: no hay que pedir cada ficha.
    uses = {item["name"]: item["recommended_for"] for item in body["items"]}
    assert uses == {
        "Nova Vision 24": "office work; programming",
        "Nova Sound Pro": "travel; office work",
    }


def test_the_listing_does_not_bring_the_tags(client: TestClient) -> None:
    body = client.get("/products", params={"limit": 1}).json()

    assert "tags" not in body["items"][0]


def test_the_listing_brings_the_image_to_show_the_card(client: TestClient) -> None:
    body = client.get("/products", params={"search": "Nova Vision"}).json()

    assert body["items"][0]["image_url"] == "https://placehold.co/800x600/png?text=MON-10000"


ENDPOINTS = ["/products?limit=1", "/categories", "/brands", "/products/MN-MON-0001"]


def test_several_consecutive_requests_to_different_endpoints_work(client: TestClient) -> None:
    # Una conexión de SQLite reusada entre requests rompe acá.
    codes = [client.get(endpoint).status_code for endpoint in ENDPOINTS * 3]

    assert codes == [200] * len(ENDPOINTS) * 3


def test_concurrent_requests_to_different_endpoints_work(client: TestClient) -> None:
    # Como los pide el navegador al cargar el listado: varios a la vez, que el
    # threadpool reparte entre hilos distintos.
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(client.get, ENDPOINTS * 6))

    assert [response.status_code for response in responses] == [200] * len(ENDPOINTS) * 6


def test_every_request_opens_and_closes_its_own_connection(
    client: TestClient, catalog_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[sqlite3.Connection] = []
    closed: list[sqlite3.Connection] = []

    @contextmanager
    def counting_scope() -> Iterator[sqlite3.Connection]:
        connection = db.connect(catalog_database)
        opened.append(connection)
        try:
            yield connection
        finally:
            closed.append(connection)
            connection.close()

    api.app.dependency_overrides[api.get_connection_scope] = lambda: counting_scope
    for endpoint in ENDPOINTS:
        assert client.get(endpoint).status_code == 200

    assert len(opened) == len(ENDPOINTS)
    assert closed == opened
    # Ninguna conexión se comparte entre requests.
    assert len({id(connection) for connection in opened}) == len(ENDPOINTS)


def test_the_connection_is_used_in_the_thread_that_created_it(
    client: TestClient, catalog_database: Path
) -> None:
    threads: list[tuple[int, int]] = []

    @contextmanager
    def recording_scope() -> Iterator[sqlite3.Connection]:
        created_in = threading.get_ident()
        with db.connection_scope(catalog_database) as connection:
            # El endpoint consulta adentro de este bloque: el hilo que la crea
            # tiene que ser el mismo que la usa, o SQLite falla.
            threads.append((created_in, threading.get_ident()))
            yield connection

    api.app.dependency_overrides[api.get_connection_scope] = lambda: recording_scope
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(client.get, ENDPOINTS * 4))

    assert threads
    assert all(created == used for created, used in threads)


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_the_api_allows_the_frontend_origin(client: TestClient, origin: str) -> None:
    response = client.get("/products", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_the_api_does_not_allow_an_unknown_origin(client: TestClient) -> None:
    response = client.get("/products", headers={"Origin": "http://sitio-ajeno.com"})

    # Sin el header, el navegador bloquea la respuesta.
    assert "access-control-allow-origin" not in response.headers


def test_the_preflight_of_the_browser_is_answered(client: TestClient) -> None:
    response = client.options(
        "/products",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_the_allowed_origins_are_the_development_ones_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)

    assert api.allowed_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_the_allowed_origins_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://mercanova.uy")

    assert api.allowed_origins() == ["https://mercanova.uy"]


def test_several_allowed_origins_are_separated_by_comma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", " https://a.uy , https://b.uy ")

    assert api.allowed_origins() == ["https://a.uy", "https://b.uy"]


@pytest.mark.parametrize("configured", ["", "   ", ",", " , "])
def test_an_empty_variable_falls_back_to_the_development_origins(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", configured)

    assert api.allowed_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_the_products_endpoint_paginates(client: TestClient) -> None:
    body = client.get("/products", params={"limit": 2, "offset": 2}).json()

    assert len(body["items"]) == 2
    assert body["has_more"] is False


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}],
)
def test_the_products_endpoint_rejects_an_invalid_pagination(
    client: TestClient, params: dict[str, int]
) -> None:
    response = client.get("/products", params=params)

    assert response.status_code == 422


def test_the_products_endpoint_rejects_an_inverted_price_range(client: TestClient) -> None:
    response = client.get("/products", params={"min_price": 500, "max_price": 100})

    assert response.status_code == 422
    assert "mínimo" in response.json()["detail"]


def test_the_product_endpoint_answers_with_the_full_detail(client: TestClient) -> None:
    response = client.get("/products/MN-MON-0001")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Nova Vision 24"
    assert body["current_price"] == 468.62
    assert body["available_qty"] == 10
    assert len(body["specifications"]) == 2


def test_the_product_endpoint_keeps_the_specification_with_the_literal_none(
    client: TestClient,
) -> None:
    body = client.get("/products/MN-HDP-0001").json()

    values = {
        specification["attribute_name"]: specification["value_text"]
        for specification in body["specifications"]
    }
    assert values["Water Resistance"] == "None"


def test_the_product_endpoint_reports_a_missing_price_as_null(client: TestClient) -> None:
    body = client.get("/products/MN-HDP-0003").json()

    assert body["current_price"] is None
    assert body["available_qty"] == 0


def test_a_product_that_does_not_exist_answers_404(client: TestClient) -> None:
    response = client.get("/products/MN-NO-EXISTE")

    assert response.status_code == 404


def test_the_404_explains_what_to_do(client: TestClient) -> None:
    detail = client.get("/products/MN-NO-EXISTE").json()["detail"]

    assert "MN-NO-EXISTE" in detail
    assert "listado de productos" in detail


def test_the_categories_endpoint_lists_the_categories(client: TestClient) -> None:
    response = client.get("/categories")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert set(body[0]) == {
        "category_id",
        "category_name",
        "subcategory_id",
        "subcategory_name",
        "department",
    }


def test_the_brands_endpoint_lists_the_brands(client: TestClient) -> None:
    response = client.get("/brands")

    assert response.status_code == 200
    body = response.json()
    assert [brand["brand_name"] for brand in body] == ["Flux", "NovaTech"]


def test_the_startup_preloads_the_model(
    with_model_preload: None, monkeypatch: pytest.MonkeyPatch, catalog_database: Path
) -> None:
    preloaded: list[bool] = []
    monkeypatch.setattr(api.llm, "preload_model", lambda: preloaded.append(True))
    api.app.dependency_overrides[api.get_connection_scope] = lambda: partial(
        db.connection_scope, catalog_database
    )
    try:
        with TestClient(api.app):
            pass
    finally:
        api.app.dependency_overrides.clear()

    # Así el primer mensaje del usuario no paga la carga del modelo.
    assert preloaded == [True]


def test_the_catalog_works_with_ollama_off(
    with_model_preload: None, monkeypatch: pytest.MonkeyPatch, catalog_database: Path
) -> None:
    def offline() -> None:
        raise api.llm.LLMConfigurationError("No se pudo hablar con Ollama. Corré: ollama serve")

    monkeypatch.setattr(api.llm, "preload_model", offline)
    api.app.dependency_overrides[api.get_connection_scope] = lambda: partial(
        db.connection_scope, catalog_database
    )
    try:
        with TestClient(api.app) as test_client:
            # Ollama apagado es una advertencia, no un error fatal: la API
            # arranca y el catálogo sigue andando.
            response = test_client.get("/products")
    finally:
        api.app.dependency_overrides.clear()

    assert response.status_code == 200


def test_the_startup_builds_the_vocabulary_of_the_catalog(
    with_vocabulary_preload: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    terms = Vocabulary()
    monkeypatch.setattr(api.vocabulary, "VOCABULARY", terms)

    with TestClient(api.app):
        pass

    # Se consulta con una base vacía: si el esquema no hubiera quedado armado en
    # el arranque, lo iría a buscar acá y fallaría.
    empty = db.connect(tmp_path / "vacia.db")
    try:
        properties = terms.schemas(empty)[0]["function"]["parameters"]["properties"]
    finally:
        empty.close()

    assert properties["category"]["enum"] == ["Headphones", "Monitors"]


def test_the_api_starts_even_if_the_database_is_not_loaded_yet(
    with_vocabulary_preload: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Si la base no está cargada al arrancar, es una advertencia: la API levanta
    # y el vocabulario se reintenta en el primer mensaje.
    monkeypatch.setattr(api.vocabulary, "VOCABULARY", Vocabulary())
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "vacia.db"))

    with TestClient(api.app) as test_client:
        response = test_client.get("/brands")

    assert response.status_code == 503
    assert "load_dataset.py" in response.json()["detail"]


def test_the_failure_of_the_preload_is_logged_as_a_warning(
    with_model_preload: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def offline() -> None:
        raise api.llm.LLMConfigurationError("Corré: ollama serve")

    monkeypatch.setattr(api.llm, "preload_model", offline)

    with caplog.at_level(logging.WARNING):
        api.preload_assistant()

    assert "ollama serve" in caplog.text


def test_an_unexpected_error_answers_a_500_in_json(
    catalog_database: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Una excepción que ningún handler específico cubre: ni CatalogError, ni
    # CartError, ni sqlite3.Error. Es la familia a la que pertenece un
    # httpx.ReadTimeout, que hoy llegaría hasta acá.
    def exploding_list(*args: object, **kwargs: object) -> None:
        raise ZeroDivisionError("ruta interna /secreta/db y detalle del stack")

    monkeypatch.setattr(api.catalog, "list_products", exploding_list)
    api.app.dependency_overrides[api.get_connection_scope] = lambda: partial(
        db.connection_scope, catalog_database
    )
    try:
        # Sin raise_server_exceptions=False el cliente de test levanta la
        # excepción y no se ve la respuesta que recibiría el usuario.
        with TestClient(api.app, raise_server_exceptions=False) as test_client:
            with caplog.at_level(logging.ERROR):
                response = test_client.get("/products")
    finally:
        api.app.dependency_overrides.clear()

    assert response.status_code == 500
    # No el "Internal Server Error" en texto plano de Starlette.
    assert response.headers["content-type"].startswith("application/json")
    assert "detail" in response.json()
    assert "error inesperado" in response.json()["detail"]
    # El mensaje real no viaja al cliente, pero sí queda en el log.
    assert "/secreta/db" not in response.text
    assert "ZeroDivisionError" not in response.text
    assert "/secreta/db" in caplog.text


def test_an_unexpected_error_does_not_take_over_the_specific_handlers(
    client: TestClient,
) -> None:
    # El handler de Exception no puede tapar los de arriba: Starlette recorre el
    # MRO y el más específico gana. Un producto inexistente sigue siendo 404.
    response = client.get("/products/MN-NO-EXISTE")

    assert response.status_code == 404
    assert "error inesperado" not in response.json()["detail"]


def test_the_api_answers_503_when_the_database_is_not_loaded(tmp_path: Path) -> None:
    empty_database = tmp_path / "vacia.db"

    api.app.dependency_overrides[api.get_connection_scope] = lambda: partial(
        db.connection_scope, empty_database
    )
    try:
        with TestClient(api.app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/products")
    finally:
        api.app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "load_dataset.py" in response.json()["detail"]
