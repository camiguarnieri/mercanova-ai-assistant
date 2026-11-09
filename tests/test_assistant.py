"""Tests de backend/assistant.py: un turno de conversación, sin Ollama.

El cliente del modelo se reemplaza por un doble: lo que se verifica es qué se le
mandó, qué herramientas se ejecutaron contra la base y qué quedó guardado.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest
from fake_ollama import (
    FakeCall,
    FakeClient,
    FakeMessage,
    FakeResponse,
    client_after_searching,
    client_that_compares,
    client_that_answers,
    client_with_one_tool_call,
)
from ollama import ResponseError

from backend import assistant, catalog_text, llm, tool_schemas, tools
from backend.sessions import SessionStore
from backend.vocabulary import Vocabulary


@pytest.fixture
def store() -> SessionStore:
    """Un almacén vacío para cada test."""
    return SessionStore()


# Corre un turno con un vocabulario propio, armado desde la base de prueba.
def respond(
    connection: sqlite3.Connection,
    store: SessionStore,
    session_id: str,
    message: str,
    *,
    client: Any,
) -> Any:
    """Llama al asistente con un vocabulario nuevo.

    Cada test arma el suyo: el vocabulario guarda en memoria el esquema que
    armó, y compartirlo entre tests arrastraría el catálogo de uno al otro.
    """
    return assistant.respond(
        connection, store, session_id, message, vocabulary=Vocabulary(), client=client
    )


def test_a_new_session_starts_with_the_system_prompt() -> None:
    messages = assistant.build_messages(None, "Quiero un monitor")

    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "Quiero un monitor"}


def test_a_session_in_progress_continues_the_conversation() -> None:
    history = [
        {"role": "system", "content": "Instrucciones"},
        {"role": "user", "content": "Quiero un monitor"},
        {"role": "assistant", "content": "¿Para qué lo vas a usar?"},
    ]

    messages = assistant.build_messages(history, "Para la oficina")

    assert len(messages) == 4
    assert messages[-1] == {"role": "user", "content": "Para la oficina"}


def test_the_previous_conversation_is_not_repeated() -> None:
    history = [{"role": "system", "content": "Instrucciones"}]

    messages = assistant.build_messages(history, "Hola")

    assert [message["role"] for message in messages].count("system") == 1


def test_the_whole_conversation_travels_to_the_model() -> None:
    # Probamos recortarla y la medición no lo respaldó: no mejoró el tiempo y el
    # modelo dejó de llamar herramientas. Está en
    # docs/decision-recorte-historial.md, y este test fija que viaja entera.
    history = [
        {"role": "system", "content": "Instrucciones"},
        {"role": "user", "content": "Quiero un monitor"},
        {"role": "tool", "tool_name": "search_products", "content": "Resultado viejo"},
        {"role": "assistant", "content": "Te recomiendo uno."},
        {"role": "user", "content": "¿Y el precio?"},
        {"role": "tool", "tool_name": "get_product_details", "content": "Resultado nuevo"},
        {"role": "assistant", "content": "Ese precio."},
    ]

    messages = assistant.build_messages(history, "Gracias")

    assert messages[:-1] == history
    assert messages[-1] == {"role": "user", "content": "Gracias"}


def test_the_answer_of_the_model_is_returned(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    turn = respond(
        catalog_connection,
        store,
        "s-1",
        "Hola",
        client=client_that_answers("¿Qué estás buscando?"),
    )

    assert turn.reply == "¿Qué estás buscando?"


def test_an_answer_without_tools_reports_no_tools(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # Cuando repregunta no consulta nada, y eso tiene que verse como tal.
    turn = respond(
        catalog_connection, store, "s-1", "Hola", client=client_that_answers("¿Para qué?")
    )

    assert turn.tools_used == []


def test_the_tool_that_was_used_is_reported_with_its_arguments(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_with_one_tool_call("search_products", {"category": "Monitors"})

    turn = respond(catalog_connection, store, "s-1", "Quiero un monitor", client=client)

    assert len(turn.tools_used) == 1
    assert turn.tools_used[0].name == "search_products"
    assert turn.tools_used[0].arguments == {"category": "Monitors"}


def test_the_reported_arguments_are_the_ones_the_tool_used(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # El modelo manda los opcionales en 'null' y los números como texto: la
    # traza muestra con qué se consultó de verdad.
    client = client_with_one_tool_call(
        "search_products", {"category": "Monitors", "brand": "null", "limit": "5"}
    )

    turn = respond(catalog_connection, store, "s-1", "Un monitor", client=client)

    assert turn.tools_used[0].arguments == {"category": "Monitors", "limit": 5}


def test_an_invented_identifier_does_not_reach_the_catalog(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # La falla reportada: el modelo armó 'MN-DOK-0001' en vez de buscar.
    client = client_with_one_tool_call("check_availability", {"product_id": "MN-DOK-0001"})

    respond(catalog_connection, store, "s-1", "¿Hay stock del dock?", client=client)

    result = json.loads(client.calls[1]["messages"][-1]["content"])
    assert result["found"] is False
    assert "no salió de ninguna búsqueda de esta conversación" in result["error"]


def test_an_identifier_of_the_catalog_is_rejected_if_it_was_not_searched(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # MN-MON-0001 existe: la regla es de procedencia, no de existencia.
    client = client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"})

    respond(catalog_connection, store, "s-1", "¿Hay stock?", client=client)

    result = json.loads(client.calls[1]["messages"][-1]["content"])
    assert result["found"] is False


def test_an_identifier_of_a_result_can_be_used_in_the_same_turn(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_after_searching("check_availability", {"product_id": "MN-MON-0001"})

    respond(catalog_connection, store, "s-1", "¿Hay stock de un monitor?", client=client)

    result = json.loads(client.calls[2]["messages"][-1]["content"])
    assert result["available_qty"] == 10


def test_an_identifier_of_a_previous_turn_can_be_used(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    respond(
        catalog_connection,
        store,
        "s-1",
        "Quiero un monitor",
        client=client_with_one_tool_call("search_products", {"category": "Monitors"}),
    )
    second = client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"})

    respond(catalog_connection, store, "s-1", "¿Y tiene stock?", client=second)

    result = json.loads(second.calls[1]["messages"][-1]["content"])
    assert result["available_qty"] == 10


def test_the_identifiers_of_a_session_do_not_pass_to_another(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    respond(
        catalog_connection,
        store,
        "s-1",
        "Quiero un monitor",
        client=client_with_one_tool_call("search_products", {"category": "Monitors"}),
    )
    other = client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"})

    respond(catalog_connection, store, "s-2", "¿Hay stock?", client=other)

    result = json.loads(other.calls[1]["messages"][-1]["content"])
    assert result["found"] is False


def test_a_failed_turn_does_not_leave_its_identifiers_usable(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # La conversación no se guardó, así que el modelo no vio esos resultados.
    class BrokenAfterSearching(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            super().chat(**kwargs)
            if len(self.calls) == 1:
                return FakeResponse(
                    FakeMessage(tool_calls=[FakeCall("search_products", {"category": "Monitors"})])
                )
            raise ConnectionError("connection refused")

    with pytest.raises(llm.LLMConfigurationError):
        respond(catalog_connection, store, "s-1", "Quiero un monitor", client=BrokenAfterSearching())

    assert store.known_products("s-1") == set()


def test_the_name_that_the_user_wrote_is_searched_before_the_model_answers(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # Ni llama3.2 ni qwen2.5 buscaban el producto que el usuario nombra.
    client = client_that_answers("Sí, lo tenemos.")

    respond(catalog_connection, store, "s-1", "¿tenés el Nova Vision 24?", client=client)

    injected = client.calls[0]["messages"][-1]
    assert injected["role"] == "tool"
    assert "Nova Vision 24" in injected["content"]


def test_the_injected_result_is_shown_in_the_trace(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    turn = respond(
        catalog_connection,
        store,
        "s-1",
        "¿tenés el Nova Vision 24?",
        client=client_that_answers("Sí."),
    )

    assert [tool.name for tool in turn.tools_used] == ["lookup_product_name"]


def test_an_injected_product_can_be_used_by_the_model(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # El product_id inyectado tiene procedencia: salió de una consulta.
    client = client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"})

    respond(catalog_connection, store, "s-1", "¿hay stock del Nova Vision 24?", client=client)

    result = json.loads(client.calls[1]["messages"][-1]["content"])
    assert result["available_qty"] == 10


def test_a_name_that_does_not_exist_is_injected_as_an_absence(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_that_answers("No lo tenemos.")

    respond(catalog_connection, store, "s-1", "¿tenés el iPhone 15 Pro?", client=client)

    injected = client.calls[0]["messages"][-1]
    assert "Ningún producto activo del catálogo se llama 'iPhone 15 Pro'" in injected["content"]


def test_a_message_without_a_name_injects_nothing(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_that_answers("¿Para qué lo vas a usar?")

    turn = respond(catalog_connection, store, "s-1", "quiero auriculares", client=client)

    assert client.calls[0]["messages"][-1]["role"] == "user"
    assert turn.tools_used == []


def test_the_products_of_a_search_travel_to_the_interface_as_data(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # Dijo que un producto es recomendado para "deportes de contacto", que no
    # existe: la tarjeta la imprime el sistema con el dato del catálogo.
    client = client_with_one_tool_call("search_products", {"category": "Monitors"})

    turn = respond(catalog_connection, store, "s-1", "quiero un monitor", client=client)

    assert [product.name for product in turn.products] == ["Flux Vision 27", "Nova Vision 24"]


def test_the_card_carries_the_price_the_stock_and_the_uses(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_with_one_tool_call("search_products", {"search": "Nova Vision 24"})

    turn = respond(catalog_connection, store, "s-1", "el Nova Vision", client=client)

    product = next(item for item in turn.products if item.product_id == "MN-MON-0001")
    assert product.current_price == 468.62
    assert product.in_stock is True
    assert product.recommended_for == "office work; programming"
    assert product.not_recommended_for == "gaming"


def test_an_empty_use_case_says_the_catalog_does_not_clarify_it(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # Le pegaron el not_recommended_for de otro producto. Ahora el campo vacío
    # viaja con la frase escrita, la misma que imprime la tarjeta: un hueco es
    # lo que el modelo completa, una frase no.
    client = client_with_one_tool_call("search_products", {"search": "Nova Sound Pro"})

    turn = respond(catalog_connection, store, "s-1", "el Nova Sound Pro", client=client)

    assert turn.products[0].not_recommended_for == catalog_text.MISSING_USES


def test_the_cards_do_not_repeat_a_product_of_two_searches(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = FakeClient(
        responses=[
            FakeResponse(
                FakeMessage(tool_calls=[FakeCall("search_products", {"category": "Monitors"})])
            ),
            FakeResponse(
                FakeMessage(tool_calls=[FakeCall("search_products", {"category": "Monitors"})])
            ),
            FakeResponse(FakeMessage(content="Esos dos.")),
        ]
    )

    turn = respond(catalog_connection, store, "s-1", "monitores", client=client)

    assert len(turn.products) == 2


def test_a_turn_without_a_search_brings_no_cards(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    turn = respond(
        catalog_connection, store, "s-1", "hola", client=client_that_answers("¡Hola!")
    )

    assert turn.products == []


def test_a_comparison_travels_to_the_interface_as_data(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # El modelo dio vuelta un valor al escribirlo en prosa: la tabla se arma
    # con el resultado de la herramienta, no con el texto.
    turn = respond(
        catalog_connection, store, "s-1", "compará esos dos", client=client_that_compares()
    )

    assert len(turn.comparisons) == 1
    assert [product.name for product in turn.comparisons[0].products] == [
        "Nova Sound Pro",
        "Flux Buds",
    ]


def test_the_comparison_carries_the_value_of_each_product(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-HDP-0001", "MN-HDP-0002"])

    comparison = assistant.comparison_of(tool_schemas.COMPARE_PRODUCTS, result)

    battery = next(
        item for item in comparison.specifications if item.attribute_name == "Battery Life"
    )
    # El 0 llega escrito con su unidad, no como dato faltante, y es el mismo
    # texto que leyó el modelo.
    assert battery.values["MN-HDP-0001"].value == "0 h"
    assert battery.values["MN-HDP-0002"].value == "26 h"
    assert battery.values["MN-HDP-0001"].name == "Nova Sound Pro"


def test_the_comparison_only_carries_what_the_table_needs(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Lo que no se manda no ocupa lugar en la respuesta.
    result = tools.compare_products(catalog_connection, ["MN-HDP-0001", "MN-HDP-0002"])

    comparison = assistant.comparison_of(tool_schemas.COMPARE_PRODUCTS, result)

    assert set(comparison.products[0].model_dump()) == {"product_id", "name"}


def test_the_result_of_another_tool_is_not_a_comparison() -> None:
    assert assistant.comparison_of("check_availability", {"found": True}) is None


def test_a_turn_without_a_comparison_brings_no_table(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    turn = respond(
        catalog_connection, store, "s-1", "hola", client=client_that_answers("¡Hola!")
    )

    assert turn.comparisons == []


def test_a_comparison_that_failed_brings_no_table(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # Un identificador inventado no se ejecuta: no hay tabla que mostrar.
    client = client_with_one_tool_call(
        "compare_products", {"product_ids": ["MN-DOK-0001", "MN-DOK-0002"]}
    )

    turn = respond(catalog_connection, store, "s-1", "compará esos", client=client)

    assert turn.comparisons == []


def test_a_tool_without_a_name_does_not_break_the_turn(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # La interfaz no la muestra, pero el turno tiene que terminar bien.
    client = FakeClient(
        responses=[
            FakeResponse(FakeMessage(tool_calls=[FakeCall(None, {})])),
            FakeResponse(FakeMessage(content="¿Qué estás buscando?")),
        ]
    )

    turn = respond(catalog_connection, store, "s-1", "hola", client=client)

    assert turn.reply == "¿Qué estás buscando?"
    assert [tool.name for tool in turn.tools_used] == [""]


def test_the_tools_are_reported_in_the_order_they_ran(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = FakeClient(
        responses=[
            FakeResponse(
                FakeMessage(tool_calls=[FakeCall("search_products", {"category": "Monitors"})])
            ),
            FakeResponse(
                FakeMessage(
                    tool_calls=[FakeCall("check_availability", {"product_id": "MN-MON-0001"})]
                )
            ),
            FakeResponse(FakeMessage(content="Te recomiendo ese.")),
        ]
    )

    turn = respond(catalog_connection, store, "s-1", "Algo para la oficina", client=client)

    assert [tool.name for tool in turn.tools_used] == ["search_products", "check_availability"]


def test_the_tool_runs_against_the_database_that_was_received(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    # Primero busca, porque el stock solo se puede consultar con un product_id
    # que haya salido de un resultado de esta conversación.
    client = client_after_searching(
        "check_availability", {"product_id": "MN-MON-0001"}, reply="Hay stock."
    )

    respond(catalog_connection, store, "s-1", "¿Hay stock?", client=client)

    # El stock que vio el modelo salió de la base de prueba, no del modelo.
    result = json.loads(client.calls[2]["messages"][-1]["content"])
    assert result["available_qty"] == 10


def test_a_tool_that_fails_is_reported_too(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_with_one_tool_call("check_availability", {"product_id": "MN-NO-EXISTE"})

    turn = respond(catalog_connection, store, "s-1", "¿Hay stock?", client=client)

    assert [tool.name for tool in turn.tools_used] == ["check_availability"]


def test_the_error_of_a_tool_travels_to_the_model_instead_of_cutting_the_turn(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_with_one_tool_call("check_availability", {"product_id": "MN-NO-EXISTE"})

    respond(catalog_connection, store, "s-1", "¿Hay stock?", client=client)

    result = json.loads(client.calls[1]["messages"][-1]["content"])
    assert result["found"] is False
    assert "MN-NO-EXISTE" in result["error"]


def test_the_catalog_tools_are_the_ones_sent_to_the_model(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_that_answers("Hola")

    respond(catalog_connection, store, "s-1", "Hola", client=client)

    sent = [schema["function"]["name"] for schema in client.calls[0]["tools"]]
    assert sent == list(tool_schemas.TOOL_NAMES)


def test_the_tools_travel_with_the_vocabulary_of_the_catalog(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_that_answers("Hola")

    respond(catalog_connection, store, "s-1", "Hola", client=client)

    search = client.calls[0]["tools"][0]["function"]["parameters"]["properties"]
    # Las categorías de la base de prueba, no las del catálogo real.
    assert search["category"]["enum"] == ["Headphones", "Monitors"]


def test_the_vocabulary_that_was_received_is_the_one_that_is_used(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    client = client_that_answers("Hola")
    terms = Vocabulary()

    assistant.respond(
        catalog_connection, store, "s-1", "Hola", vocabulary=terms, client=client
    )

    assert client.calls[0]["tools"] == terms.schemas(catalog_connection)


def test_the_conversation_is_saved_in_the_session(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    respond(
        catalog_connection, store, "s-1", "Hola", client=client_that_answers("Hola, ¿qué buscás?")
    )

    history = store.history("s-1")
    assert history[-1] == {"role": "assistant", "content": "Hola, ¿qué buscás?"}


def test_the_second_message_arrives_with_the_previous_conversation(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    respond(
        catalog_connection, store, "s-1", "Quiero un monitor",
        client=client_that_answers("¿Para qué lo vas a usar?"),
    )
    second = client_that_answers("Te recomiendo uno de oficina.")

    respond(catalog_connection, store, "s-1", "Para la oficina", client=second)

    sent = second.calls[0]["messages"]
    assert [message["content"] for message in sent[1:]] == [
        "Quiero un monitor",
        "¿Para qué lo vas a usar?",
        "Para la oficina",
    ]


def test_another_session_starts_from_zero(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    respond(
        catalog_connection, store, "s-1", "Quiero un monitor",
        client=client_that_answers("¿Para qué?"),
    )
    other = client_that_answers("Hola")

    respond(catalog_connection, store, "s-2", "Hola", client=other)

    # Solo el prompt del sistema y el mensaje nuevo: nada de la otra sesión.
    assert len(other.calls[0]["messages"]) == 2


def test_only_the_tools_of_this_turn_are_reported(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    respond(
        catalog_connection, store, "s-1", "¿Hay stock?",
        client=client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"}),
    )

    turn = respond(
        catalog_connection, store, "s-1", "Gracias", client=client_that_answers("De nada.")
    )

    assert turn.tools_used == []


def test_a_failed_turn_does_not_save_a_half_conversation(
    catalog_connection: sqlite3.Connection, store: SessionStore
) -> None:
    class OfflineClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise ConnectionError("connection refused")

    with pytest.raises(llm.LLMConfigurationError):
        respond(catalog_connection, store, "s-1", "Hola", client=OfflineClient())

    assert store.history("s-1") is None


def test_an_error_of_ollama_arrives_actionable(
    catalog_connection: sqlite3.Connection,
    store: SessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "falta-este")

    class MissingModelClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise ResponseError("model not found", 404)

    with pytest.raises(llm.LLMConfigurationError) as error:
        respond(catalog_connection, store, "s-1", "Hola", client=MissingModelClient())

    assert "ollama pull falta-este" in str(error.value)
