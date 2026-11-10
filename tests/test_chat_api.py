"""Tests de backend/chat_api.py: el endpoint POST /chat con el cliente de test.

El cliente de Ollama se reemplaza con `llm.Client`, así que ningún test prende
el modelo ni sale a la red.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from fake_ollama import (
    FakeClient,
    FakeResponse,
    client_after_searching,
    client_that_answers,
    client_that_compares,
    client_with_one_tool_call,
)
from fastapi.testclient import TestClient
from ollama import ResponseError

from backend import api, db, dependencies, llm
from backend.carts import CartStore
from backend.sessions import SessionStore
from backend.vocabulary import Vocabulary


@pytest.fixture
def store() -> SessionStore:
    """Un almacén de conversaciones vacío, propio de cada test."""
    return SessionStore()


@pytest.fixture
def terms() -> Vocabulary:
    """Un vocabulario propio de cada test, para que no comparta el esquema."""
    return Vocabulary()


@pytest.fixture
def cart_store() -> CartStore:
    """Un almacén de carritos vacío, propio de cada test."""
    return CartStore()


@pytest.fixture
def client(
    catalog_database: Path, store: SessionStore, cart_store: CartStore, terms: Vocabulary
) -> Iterator[TestClient]:
    """Un cliente de test con la base de prueba y una sesión limpia."""
    api.app.dependency_overrides[api.get_connection_scope] = lambda: partial(
        db.connection_scope, catalog_database
    )
    api.app.dependency_overrides[dependencies.get_session_store] = lambda: store
    api.app.dependency_overrides[dependencies.get_cart_store] = lambda: cart_store
    api.app.dependency_overrides[dependencies.get_vocabulary] = lambda: terms
    with TestClient(api.app) as test_client:
        yield test_client
    api.app.dependency_overrides.clear()


# Hace que el asistente use el doble en vez de hablar con Ollama.
def use_model(monkeypatch: pytest.MonkeyPatch, fake: FakeClient) -> FakeClient:
    """Reemplaza el cliente de Ollama por uno preparado.

    Args:
        monkeypatch: El fixture de pytest que deshace el cambio al terminar.
        fake: El doble que va a contestar.

    Returns:
        El mismo doble, para poder revisar después qué se le mandó.
    """
    monkeypatch.setattr(llm, "Client", lambda **kwargs: fake)
    return fake


def test_the_chat_answers_with_the_reply_of_the_assistant(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("¿Para qué lo vas a usar?"))

    response = client.post("/chat", json={"session_id": "s-1", "message": "Quiero un monitor"})

    assert response.status_code == 200
    assert response.json()["reply"] == "¿Para qué lo vas a usar?"


def test_the_chat_returns_the_expected_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("Hola"))

    body = client.post("/chat", json={"session_id": "s-1", "message": "Hola"}).json()

    assert set(body) == {"session_id", "reply", "products", "comparisons", "tools_used"}


def test_the_chat_echoes_the_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("Hola"))

    body = client.post("/chat", json={"session_id": "s-1", "message": "Hola"}).json()

    assert body["session_id"] == "s-1"


def test_the_chat_reports_the_tool_it_used(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(
        monkeypatch,
        client_with_one_tool_call("search_products", {"category": "Monitors", "max_price": 500}),
    )

    body = client.post("/chat", json={"session_id": "s-1", "message": "Un monitor"}).json()

    assert body["tools_used"] == [
        {"name": "search_products", "arguments": {"category": "Monitors", "max_price": 500}}
    ]


def test_an_answer_without_tools_reports_an_empty_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("¿Qué buscás?"))

    body = client.post("/chat", json={"session_id": "s-1", "message": "Hola"}).json()

    assert body["tools_used"] == []


def test_the_conversation_is_kept_between_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("¿Para qué lo vas a usar?"))
    client.post("/chat", json={"session_id": "s-1", "message": "Quiero un monitor"})

    second = use_model(monkeypatch, client_that_answers("Te recomiendo uno de oficina."))
    client.post("/chat", json={"session_id": "s-1", "message": "Para la oficina"})

    sent = second.calls[0]["messages"]
    assert [message["content"] for message in sent[1:]] == [
        "Quiero un monitor",
        "¿Para qué lo vas a usar?",
        "Para la oficina",
    ]


def test_the_client_does_not_send_the_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("Hola"))

    response = client.post(
        "/chat",
        json={"session_id": "s-1", "message": "Hola", "history": []},
    )

    assert response.status_code == 422


def test_the_conversation_is_stored_by_session(
    client: TestClient, store: SessionStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("Hola"))

    client.post("/chat", json={"session_id": "s-1", "message": "Hola"})
    client.post("/chat", json={"session_id": "s-2", "message": "Hola"})

    assert store.count() == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "Hola"},
        {"session_id": "s-1"},
        {"session_id": "", "message": "Hola"},
        {"session_id": "s-1", "message": ""},
        {"session_id": "s-1", "message": "   "},
    ],
)
def test_an_invalid_request_is_rejected(client: TestClient, payload: dict[str, str]) -> None:
    assert client.post("/chat", json=payload).status_code == 422


def test_an_invented_identifier_comes_back_as_a_correctable_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # La falla reportada, de punta a punta: el modelo armó 'MN-DOK-0001'.
    fake = use_model(
        monkeypatch,
        client_with_one_tool_call("check_availability", {"product_id": "MN-DOK-0001"}),
    )

    response = client.post(
        "/chat", json={"session_id": "s-1", "message": "¿hay stock del dock?"}
    )

    assert response.status_code == 200
    result = json.loads(fake.calls[1]["messages"][-1]["content"])
    assert "no salió de ninguna búsqueda de esta conversación" in result["error"]


def test_the_identifiers_are_kept_between_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_with_one_tool_call("search_products", {"category": "Monitors"}))
    client.post("/chat", json={"session_id": "s-1", "message": "quiero un monitor"})

    second = use_model(
        monkeypatch,
        client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"}),
    )
    client.post("/chat", json={"session_id": "s-1", "message": "¿y tiene stock?"})

    result = json.loads(second.calls[1]["messages"][-1]["content"])
    assert result["available_qty"] == 10


def test_a_new_session_does_not_inherit_the_identifiers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_with_one_tool_call("search_products", {"category": "Monitors"}))
    client.post("/chat", json={"session_id": "s-1", "message": "quiero un monitor"})

    other = use_model(
        monkeypatch,
        client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"}),
    )
    client.post("/chat", json={"session_id": "s-2", "message": "¿hay stock?"})

    result = json.loads(other.calls[1]["messages"][-1]["content"])
    assert result["found"] is False


def test_the_products_of_a_search_come_back_as_data_for_the_cards(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_with_one_tool_call("search_products", {"category": "Monitors"}))

    body = client.post("/chat", json={"session_id": "s-1", "message": "un monitor"}).json()

    assert [product["name"] for product in body["products"]] == [
        "Flux Vision 27",
        "Nova Vision 24",
    ]


def test_the_card_only_carries_what_it_shows(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_with_one_tool_call("search_products", {"category": "Monitors"}))

    body = client.post("/chat", json={"session_id": "s-1", "message": "un monitor"}).json()

    assert set(body["products"][0]) == {
        "product_id",
        "name",
        "brand",
        "currency",
        "current_price",
        "in_stock",
        "recommended_for",
        "not_recommended_for",
    }


def test_the_name_that_the_user_wrote_comes_back_searched(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # El paso determinístico: el catálogo se consulta antes del modelo.
    use_model(monkeypatch, client_that_answers("Sí, lo tenemos."))

    body = client.post(
        "/chat", json={"session_id": "s-1", "message": "¿tenés el Nova Vision 24?"}
    ).json()

    assert [tool["name"] for tool in body["tools_used"]] == ["lookup_product_name"]
    assert body["products"][0]["name"] == "Nova Vision 24"


def test_a_name_that_does_not_exist_comes_back_without_products(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("No lo tenemos."))

    body = client.post(
        "/chat", json={"session_id": "s-1", "message": "¿tenés el iPhone 15 Pro?"}
    ).json()

    assert body["products"] == []
    assert [tool["name"] for tool in body["tools_used"]] == ["lookup_product_name"]


def test_a_message_without_a_name_does_not_consult_anything(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("¿Para qué lo vas a usar?"))

    body = client.post(
        "/chat", json={"session_id": "s-1", "message": "quiero auriculares"}
    ).json()

    assert body["tools_used"] == []
    assert body["products"] == []


def test_a_comparison_comes_back_as_data_for_the_table(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # El modelo escribió un valor al revés en la prosa: la tabla sale del
    # payload de la herramienta, no del texto.
    use_model(monkeypatch, client_that_compares())

    body = client.post("/chat", json={"session_id": "s-1", "message": "compará esos"}).json()

    assert len(body["comparisons"]) == 1
    assert [product["name"] for product in body["comparisons"][0]["products"]] == [
        "Nova Sound Pro",
        "Flux Buds",
    ]


def test_the_comparison_writes_a_value_of_zero_with_its_unit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_compares())

    body = client.post("/chat", json={"session_id": "s-1", "message": "compará esos"}).json()

    battery = next(
        item
        for item in body["comparisons"][0]["specifications"]
        if item["attribute_name"] == "Battery Life"
    )
    # La celda viaja ya escrita, con el nombre del producto al que pertenece:
    # es el mismo texto que recibió el modelo.
    assert battery["values"]["MN-HDP-0001"] == {"name": "Nova Sound Pro", "value": "0 h"}


def test_a_turn_without_a_comparison_brings_an_empty_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("¡Hola!"))

    body = client.post("/chat", json={"session_id": "s-1", "message": "hola"}).json()

    assert body["comparisons"] == []


def test_the_chat_answers_503_when_ollama_is_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class OfflineClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise ConnectionError("connection refused")

    use_model(monkeypatch, OfflineClient())

    response = client.post("/chat", json={"session_id": "s-1", "message": "Hola"})

    # No un 500 pelado: el frontend tiene que poder mostrar qué hacer.
    assert response.status_code == 503
    assert "ollama serve" in response.json()["detail"]


def test_the_503_explains_how_to_install_a_missing_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "falta-este")

    class MissingModelClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise ResponseError("model not found", 404)

    use_model(monkeypatch, MissingModelClient())

    response = client.post("/chat", json={"session_id": "s-1", "message": "Hola"})

    assert response.status_code == 503
    assert "ollama pull falta-este" in response.json()["detail"]


def test_the_503_explains_an_unusable_answer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # El modelo contesta vacío y sin pedir herramientas: no hay nada que mostrar.
    use_model(monkeypatch, client_that_answers(""))

    response = client.post("/chat", json={"session_id": "s-1", "message": "Hola"})

    assert response.status_code == 503
    assert "vacío" in response.json()["detail"]


def test_a_failed_turn_does_not_leave_the_session_started(
    client: TestClient, store: SessionStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    class OfflineClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise ConnectionError("connection refused")

    use_model(monkeypatch, OfflineClient())

    client.post("/chat", json={"session_id": "s-1", "message": "Hola"})

    assert store.history("s-1") is None


def test_the_browser_can_post_to_the_chat(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(monkeypatch, client_that_answers("Hola"))

    response = client.post(
        "/chat",
        json={"session_id": "s-1", "message": "Hola"},
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_the_preflight_of_the_chat_is_answered(client: TestClient) -> None:
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]


def test_the_assistant_adds_to_the_cart_the_user_sees(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(
        monkeypatch,
        client_after_searching(
            "add_to_cart", {"product_id": "MN-MON-0001", "quantity": 2}, reply="Lo agregué."
        ),
    )

    response = client.post("/chat", json={"session_id": "s-1", "message": "llevame dos"})

    assert response.status_code == 200
    assert [tool["name"] for tool in response.json()["tools_used"]][-1] == "add_to_cart"
    # El carrito que escribió el asistente es el que devuelve GET /cart: es el
    # mismo almacén, así la pantalla y la conversación no pueden discrepar.
    cart = client.get("/cart", params={"session_id": "s-1"}).json()
    assert cart["item_count"] == 2
    assert cart["items"][0]["product_id"] == "MN-MON-0001"


def test_the_assistant_writes_only_the_cart_of_its_own_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(
        monkeypatch,
        client_after_searching("add_to_cart", {"product_id": "MN-MON-0001"}, reply="Listo."),
    )

    client.post("/chat", json={"session_id": "s-1", "message": "llevame uno"})

    assert client.get("/cart", params={"session_id": "s-2"}).json()["items"] == []


def test_the_assistant_cannot_confirm_a_purchase(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(
        monkeypatch,
        client_with_one_tool_call("checkout", {"session_id": "s-1"}, reply="No puedo."),
    )

    client.post("/chat", json={"session_id": "s-1", "message": "comprá todo"})

    # No existe una herramienta para cerrar la compra: la orden la crea el
    # usuario desde POST /checkout, con su confirmación explícita.
    assert client.get("/orders", params={"session_id": "s-1"}).json() == []
