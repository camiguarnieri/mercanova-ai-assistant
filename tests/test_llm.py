"""Tests de backend/llm.py con un cliente falso.

Ningún test prende Ollama ni sale a la red: se reemplaza el cliente por un doble
y se verifica **qué se le mandó al modelo**, no qué contestó.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ollama import RequestError, ResponseError

from backend import llm, tool_schemas


class FakeFunction:
    """La función que el modelo dice querer invocar."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.name = name
        self.arguments = arguments


class FakeCall:
    """Una invocación de herramienta pedida por el modelo."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    """El mensaje que devuelve el modelo."""

    def __init__(self, content: str = "", tool_calls: list[FakeCall] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class FakeResponse:
    """La respuesta de `chat()`."""

    def __init__(self, message: FakeMessage | None) -> None:
        self.message = message


class FakeClient:
    """Cliente que devuelve respuestas preparadas y guarda lo que recibió."""

    def __init__(self, *, responses: list[FakeResponse] | None = None, **kwargs: Any) -> None:
        self.host = kwargs.get("host")
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> FakeResponse:
        # Se guarda una copia de los mensajes: la lista que recibe se sigue
        # llenando entre vueltas, y si no se copia todas apuntan a lo mismo.
        self.calls.append({**kwargs, "messages": list(kwargs.get("messages") or [])})
        if not self.responses:
            return FakeResponse(FakeMessage(content="Listo."))
        return self.responses.pop(0)


# Devuelve un cliente que pide una herramienta y después responde.
def client_with_one_tool_call(name: str, arguments: dict[str, Any]) -> FakeClient:
    """Arma el doble para una conversación de una vuelta de herramientas."""
    return FakeClient(
        responses=[
            FakeResponse(FakeMessage(tool_calls=[FakeCall(name, arguments)])),
            FakeResponse(FakeMessage(content="Te recomiendo ese producto.")),
        ]
    )


def test_the_model_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")

    assert llm.model_name() == "test-model"


@pytest.mark.parametrize("configured", ["", "   "])
def test_an_empty_model_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", configured)

    assert llm.model_name() == llm.DEFAULT_MODEL


def test_the_model_has_a_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    assert llm.model_name() == llm.DEFAULT_MODEL


def test_the_host_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://otro-host:11434")

    assert llm.host() == "http://otro-host:11434"


def test_the_host_has_a_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    assert llm.host() == llm.DEFAULT_HOST


def test_the_client_is_created_against_the_configured_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://otro-host:11434")
    monkeypatch.setattr(llm, "Client", FakeClient)

    assert llm.create_client().host == "http://otro-host:11434"


def test_preloading_asks_ollama_to_load_the_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    client = FakeClient()

    llm.preload_model(client)

    assert client.calls[0]["model"] == "test-model"


def test_preloading_sends_no_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()

    llm.preload_model(client)

    # Sin mensajes: solo se busca que el modelo quede en memoria.
    assert client.calls[0]["messages"] == []


def test_preloading_keeps_the_model_in_memory() -> None:
    client = FakeClient()

    llm.preload_model(client)

    assert client.calls[0]["keep_alive"] == llm.KEEP_ALIVE


def test_preloading_explains_how_to_install_a_missing_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "falta-este")

    class MissingModelClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise ResponseError("model not found", 404)

    with pytest.raises(llm.LLMConfigurationError) as error:
        llm.preload_model(MissingModelClient())

    assert "ollama pull falta-este" in str(error.value)


def test_preloading_explains_how_to_start_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    class OfflineClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise ConnectionError("connection refused")

    with pytest.raises(llm.LLMConfigurationError) as error:
        llm.preload_model(OfflineClient())

    assert "ollama serve" in str(error.value)
    assert "http://localhost:11434" in str(error.value)


def test_a_request_error_is_translated_too() -> None:
    class BrokenClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise RequestError("host inválido")

    with pytest.raises(llm.LLMConfigurationError):
        llm.preload_model(BrokenClient())


def test_the_conversation_starts_with_the_system_prompt() -> None:
    messages = llm.start_conversation("Quiero un monitor")

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == llm.SYSTEM_PROMPT
    assert messages[1] == {"role": "user", "content": "Quiero un monitor"}


def test_the_conversation_can_use_another_system_prompt() -> None:
    messages = llm.start_conversation("Hola", system_prompt="Instrucciones de prueba.")

    assert messages[0]["content"] == "Instrucciones de prueba."


def test_the_tools_are_sent_to_the_model() -> None:
    client = FakeClient()

    llm.run_conversation(
        llm.start_conversation("Hola"),
        tools=tool_schemas.TOOL_SCHEMAS,
        execute_tool=lambda name, arguments: {},
        client=client,
    )

    assert client.calls[0]["tools"] == tool_schemas.TOOL_SCHEMAS


def test_the_temperature_is_zero() -> None:
    client = FakeClient()

    llm.run_conversation(
        llm.start_conversation("Hola"),
        tools=[],
        execute_tool=lambda name, arguments: {},
        client=client,
    )

    assert client.calls[0]["options"] == {"temperature": 0}


def test_the_configured_model_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    client = FakeClient()

    llm.run_conversation(
        llm.start_conversation("Hola"),
        tools=[],
        execute_tool=lambda name, arguments: {},
        client=client,
    )

    assert client.calls[0]["model"] == "test-model"


def test_the_history_ends_with_the_answer_of_the_model() -> None:
    client = FakeClient(responses=[FakeResponse(FakeMessage(content="Hay 10 unidades."))])

    history = llm.run_conversation(
        llm.start_conversation("Hola"),
        tools=[],
        execute_tool=lambda name, arguments: {},
        client=client,
    )

    assert history[-1] == {"role": "assistant", "content": "Hay 10 unidades."}


def test_the_requested_tool_is_executed_with_its_arguments() -> None:
    executed: list[tuple[str, dict[str, Any]]] = []
    client = client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"})

    llm.run_conversation(
        llm.start_conversation("¿Hay stock?"),
        tools=tool_schemas.TOOL_SCHEMAS,
        execute_tool=lambda name, arguments: executed.append((name, arguments)) or {"found": True},
        client=client,
    )

    assert executed == [("check_availability", {"product_id": "MN-MON-0001"})]


def test_the_result_of_the_tool_travels_back_as_json() -> None:
    client = client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"})

    history = llm.run_conversation(
        llm.start_conversation("¿Hay stock?"),
        tools=tool_schemas.TOOL_SCHEMAS,
        execute_tool=lambda name, arguments: {"available_qty": 10, "in_stock": True},
        client=client,
    )

    tool_message = history[3]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_name"] == "check_availability"
    assert json.loads(tool_message["content"]) == {"available_qty": 10, "in_stock": True}


def test_the_model_sees_the_result_in_the_following_turn() -> None:
    client = client_with_one_tool_call("check_availability", {"product_id": "MN-MON-0001"})

    llm.run_conversation(
        llm.start_conversation("¿Hay stock?"),
        tools=tool_schemas.TOOL_SCHEMAS,
        execute_tool=lambda name, arguments: {"available_qty": 10},
        client=client,
    )

    second_turn = client.calls[1]["messages"]
    assert second_turn[-1]["role"] == "tool"
    assert "available_qty" in second_turn[-1]["content"]


def test_the_model_can_ask_for_several_tools_before_answering() -> None:
    client = FakeClient(
        responses=[
            FakeResponse(FakeMessage(tool_calls=[FakeCall("list_categories", {})])),
            FakeResponse(FakeMessage(tool_calls=[FakeCall("search_products", {"limit": 2})])),
            FakeResponse(
                FakeMessage(tool_calls=[FakeCall("check_availability", {"product_id": "X"})])
            ),
            FakeResponse(FakeMessage(content="Te recomiendo ese.")),
        ]
    )

    history = llm.run_conversation(
        llm.start_conversation("Quiero algo para la oficina"),
        tools=tool_schemas.TOOL_SCHEMAS,
        execute_tool=lambda name, arguments: {"found": True},
        client=client,
    )

    assert len(client.calls) == 4
    assert [message["role"] for message in history].count("tool") == 3
    assert history[-1]["content"] == "Te recomiendo ese."


def test_several_tools_in_one_turn_are_all_executed() -> None:
    executed: list[str] = []
    client = FakeClient(
        responses=[
            FakeResponse(
                FakeMessage(
                    tool_calls=[
                        FakeCall("check_availability", {"product_id": "A"}),
                        FakeCall("check_availability", {"product_id": "B"}),
                    ]
                )
            ),
            FakeResponse(FakeMessage(content="Los dos tienen stock.")),
        ]
    )

    llm.run_conversation(
        llm.start_conversation("¿Hay stock de los dos?"),
        tools=tool_schemas.TOOL_SCHEMAS,
        execute_tool=lambda name, arguments: executed.append(arguments["product_id"]) or {},
        client=client,
    )

    assert executed == ["A", "B"]


def test_the_loop_stops_after_the_limit_of_steps() -> None:
    # El modelo pide herramientas para siempre: no se puede quedar en bucle.
    client = FakeClient(
        responses=[
            FakeResponse(FakeMessage(tool_calls=[FakeCall("list_categories", {})]))
            for _ in range(10)
        ]
    )

    with pytest.raises(llm.LLMResponseError) as error:
        llm.run_conversation(
            llm.start_conversation("Hola"),
            tools=tool_schemas.TOOL_SCHEMAS,
            execute_tool=lambda name, arguments: {},
            client=client,
            max_steps=3,
        )

    assert "3 vueltas" in str(error.value)
    assert len(client.calls) == 4


def test_the_conversation_received_is_not_modified() -> None:
    messages = llm.start_conversation("Hola")
    original = len(messages)
    client = client_with_one_tool_call("list_categories", {})

    llm.run_conversation(
        messages,
        tools=tool_schemas.TOOL_SCHEMAS,
        execute_tool=lambda name, arguments: {},
        client=client,
    )

    assert len(messages) == original


def test_an_answer_without_a_message_is_rejected() -> None:
    client = FakeClient(responses=[FakeResponse(None)])

    with pytest.raises(llm.LLMResponseError) as error:
        llm.run_conversation(
            llm.start_conversation("Hola"),
            tools=[],
            execute_tool=lambda name, arguments: {},
            client=client,
        )

    assert "sin mensaje" in str(error.value)


@pytest.mark.parametrize("content", ["", "   "])
def test_an_empty_answer_without_tools_is_rejected(content: str) -> None:
    client = FakeClient(responses=[FakeResponse(FakeMessage(content=content))])

    with pytest.raises(llm.LLMResponseError) as error:
        llm.run_conversation(
            llm.start_conversation("Hola"),
            tools=[],
            execute_tool=lambda name, arguments: {},
            client=client,
        )

    assert "vacío" in str(error.value)


def test_an_error_of_ollama_during_the_conversation_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "falta-este")

    class MissingModelClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise ResponseError("model 'falta-este' not found", 404)

    with pytest.raises(llm.LLMConfigurationError) as error:
        llm.run_conversation(
            llm.start_conversation("Hola"),
            tools=[],
            execute_tool=lambda name, arguments: {},
            client=MissingModelClient(),
        )

    assert "ollama pull falta-este" in str(error.value)


def test_a_message_without_tool_calls_has_no_calls() -> None:
    assert llm.tool_calls_of(FakeMessage(content="Hola")) == []


def test_the_default_limit_of_steps_is_low_enough_to_not_hang() -> None:
    assert 1 <= llm.MAX_TOOL_STEPS <= 10
