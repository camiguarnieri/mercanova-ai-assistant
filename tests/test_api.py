"""Tests de backend/api.py: los endpoints del catálogo con el cliente de test."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import api, db


@pytest.fixture
def client(catalog_database: Path) -> Iterator[TestClient]:
    """Un cliente de test apuntado a la base de prueba, no a la real."""

    def connection_for_test() -> Iterator[sqlite3.Connection]:
        connection = db.connect(catalog_database)
        try:
            yield connection
        finally:
            connection.close()

    api.app.dependency_overrides[api.get_connection] = connection_for_test
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


def test_the_api_answers_503_when_the_database_is_not_loaded(tmp_path: Path) -> None:
    empty_database = tmp_path / "vacia.db"

    def connection_without_schema() -> Iterator[sqlite3.Connection]:
        connection = db.connect(empty_database)
        try:
            yield connection
        finally:
            connection.close()

    api.app.dependency_overrides[api.get_connection] = connection_without_schema
    try:
        with TestClient(api.app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/products")
    finally:
        api.app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "load_dataset.py" in response.json()["detail"]
