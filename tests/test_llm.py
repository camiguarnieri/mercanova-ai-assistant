"""Tests de backend/llm.py con un cliente falso.

Ningún test prende Ollama ni sale a la red: se reemplaza el cliente por un doble
y se verifica **qué se le mandó al modelo**, no qué contestó.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from ollama import RequestError, ResponseError

from fake_ollama import (
    FakeCall,
    FakeClient,
    FakeMessage,
    FakeResponse,
    client_with_one_tool_call,
)

from backend import llm, tool_schemas


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

    assert client.calls[0]["keep_alive"] == llm.keep_alive()


def test_preloading_uses_the_same_options_as_a_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ollama carga el modelo con la ventana del pedido: si se precarga con otra,
    # lo recarga en el primer mensaje y la precarga no sirvió de nada.
    monkeypatch.setenv("OLLAMA_NUM_CTX", "2048")
    client = FakeClient()

    llm.preload_model(client)

    assert client.calls[0]["options"] == llm.options()


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


def test_the_timeout_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_TIMEOUT", "45")

    assert llm.timeout_seconds() == 45.0


@pytest.mark.parametrize("configured", ["", "   "])
def test_an_empty_timeout_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    monkeypatch.setenv("OLLAMA_TIMEOUT", configured)

    assert llm.timeout_seconds() == llm.DEFAULT_TIMEOUT


def test_the_timeout_has_a_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)

    assert llm.timeout_seconds() == llm.DEFAULT_TIMEOUT


def test_the_default_timeout_is_generous_enough_for_cpu() -> None:
    # El turno más lento de corrida.log tardó 431.4s con una vuelta de
    # herramientas: dos llamadas al modelo, unos 215s cada una. Un timeout por
    # llamada por debajo de eso cortaría una conversación que hoy funciona.
    assert llm.DEFAULT_TIMEOUT >= 215.0


@pytest.mark.parametrize("configured", ["cero", "0", "-30", "nan", "inf"])
def test_a_timeout_that_is_not_a_positive_number_is_rejected(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    # Con 'inf' el timeout volvería a ser infinito, que es lo que esto evita.
    monkeypatch.setenv("OLLAMA_TIMEOUT", configured)

    with pytest.raises(llm.LLMConfigurationError) as error:
        llm.timeout_seconds()

    assert "OLLAMA_TIMEOUT" in str(error.value)


def test_the_client_is_created_with_the_configured_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sin esto el cliente queda con el default de la librería, que es esperar
    # para siempre.
    monkeypatch.setenv("OLLAMA_TIMEOUT", "90")
    monkeypatch.setattr(llm, "Client", FakeClient)

    assert llm.create_client().timeout == 90.0


def test_the_client_is_created_with_a_timeout_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    monkeypatch.setattr(llm, "Client", FakeClient)

    assert llm.create_client().timeout == llm.DEFAULT_TIMEOUT


def test_a_read_timeout_is_translated_to_a_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # httpx.ReadTimeout no hereda de OSError: sin nombrarlo subía crudo hasta el
    # handler genérico de la API y el usuario veía un 500 sin explicación.
    monkeypatch.setenv("OLLAMA_TIMEOUT", "120")

    class SlowClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise httpx.ReadTimeout("timed out")

    with pytest.raises(llm.LLMTimeoutError) as error:
        llm.run_conversation(
            llm.start_conversation("Hola"),
            tools=[],
            execute_tool=lambda name, arguments: {},
            client=SlowClient(),
        )

    # El mensaje dice qué hacer y con qué número se cortó, sin inventarlo.
    assert "tardando demasiado" in str(error.value)
    assert "120" in str(error.value)
    assert "OLLAMA_TIMEOUT" in str(error.value)


def test_a_read_timeout_during_the_preload_is_translated_too() -> None:
    class SlowClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise httpx.ReadTimeout("timed out")

    with pytest.raises(llm.LLMTimeoutError) as error:
        llm.preload_model(SlowClient())

    assert "tardando demasiado" in str(error.value)


def test_a_connect_timeout_is_a_timeout_too() -> None:
    # Es otra rama de httpx.TimeoutException: para el usuario es lo mismo.
    class SlowClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise httpx.ConnectTimeout("timed out")

    with pytest.raises(llm.LLMTimeoutError):
        llm.preload_model(SlowClient())


def test_a_broken_response_is_translated_to_a_timeout_error() -> None:
    # Ollama se murió a mitad de la respuesta: típicamente se quedó sin memoria.
    class DyingClient(FakeClient):
        def chat(self, **kwargs: Any) -> FakeResponse:
            raise httpx.RemoteProtocolError("server disconnected")

    with pytest.raises(llm.LLMTimeoutError) as error:
        llm.preload_model(DyingClient())

    assert "cortó la respuesta" in str(error.value)
    assert "ollama serve" in str(error.value)


def test_a_timeout_error_is_an_llm_error() -> None:
    # Es lo que hace que termine en el 503 de chat_api, que captura LLMError.
    assert issubclass(llm.LLMTimeoutError, llm.LLMError)
    assert not issubclass(llm.LLMTimeoutError, llm.LLMConfigurationError)


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

    assert client.calls[0]["options"]["temperature"] == 0


def test_the_context_window_travels_in_the_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_NUM_CTX", "2048")
    client = FakeClient()

    llm.run_conversation(
        llm.start_conversation("Hola"),
        tools=[],
        execute_tool=lambda name, arguments: {},
        client=client,
    )

    assert client.calls[0]["options"] == {"temperature": 0, "num_ctx": 2048}


def test_the_answer_length_travels_in_the_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # En CPU cada token generado se paga en tiempo: el tope de la respuesta
    # viaja en cada pedido, no solo en la precarga.
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "120")
    client = FakeClient()

    llm.run_conversation(
        llm.start_conversation("Hola"),
        tools=[],
        execute_tool=lambda name, arguments: {},
        client=client,
    )

    assert client.calls[0]["options"]["num_predict"] == 120


def test_the_answer_length_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "500")

    assert llm.num_predict() == 500


@pytest.mark.parametrize("configured", ["", "   "])
def test_without_the_answer_length_there_is_no_limit_of_ours(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    # No tiene default a propósito: probamos con 300 y cortó una respuesta a
    # mitad de palabra. Sin la variable el tope lo decide Ollama.
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", configured)

    assert llm.num_predict() is None


@pytest.mark.parametrize("configured", ["", "   "])
def test_without_the_answer_length_the_option_does_not_travel(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    # Mandar num_predict en null no es lo mismo que no mandarlo.
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", configured)

    assert "num_predict" not in llm.options()


@pytest.mark.parametrize("configured", ["muchos", "0", "-100", "300.5"])
def test_an_answer_length_that_is_not_a_positive_integer_is_reported(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    # No se ignora en silencio: si alguien la escribió mal, hay que avisarle.
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", configured)

    with pytest.raises(llm.LLMConfigurationError) as error:
        llm.num_predict()

    assert "OLLAMA_NUM_PREDICT" in str(error.value)
    assert "lo decida Ollama" in str(error.value)


def test_how_long_the_model_stays_loaded_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "1h")

    assert llm.keep_alive() == "1h"


@pytest.mark.parametrize("configured", ["", "   "])
def test_without_the_keep_alive_the_default_one_is_used(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", configured)

    assert llm.keep_alive() == llm.DEFAULT_KEEP_ALIVE


def test_the_keep_alive_is_not_validated_here(monkeypatch: pytest.MonkeyPatch) -> None:
    # El formato lo interpreta Ollama: acepta una duración, segundos o "-1".
    # Validarlo acá sería adivinar su gramática.
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "-1")

    assert llm.keep_alive() == "-1"


def test_the_keep_alive_travels_in_every_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "45m")
    client = FakeClient()

    llm.run_conversation(
        llm.start_conversation("Hola"),
        tools=[],
        execute_tool=lambda name, arguments: {},
        client=client,
    )

    assert client.calls[0]["keep_alive"] == "45m"


def test_the_context_window_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")

    assert llm.num_ctx() == 16384


@pytest.mark.parametrize("configured", ["", "   "])
def test_an_empty_context_window_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    monkeypatch.setenv("OLLAMA_NUM_CTX", configured)

    assert llm.num_ctx() == llm.DEFAULT_NUM_CTX


def test_the_context_window_has_a_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

    assert llm.num_ctx() == llm.DEFAULT_NUM_CTX


def test_the_default_context_window_leaves_room_for_the_conversation() -> None:
    # El prompt del sistema más los esquemas ocupan unos 2800 tokens.
    assert llm.DEFAULT_NUM_CTX == 8192


@pytest.mark.parametrize("configured", ["ocho mil", "8192 tokens", "8.5"])
def test_a_context_window_that_is_not_a_number_is_rejected(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    monkeypatch.setenv("OLLAMA_NUM_CTX", configured)

    with pytest.raises(llm.LLMConfigurationError) as error:
        llm.num_ctx()

    assert "OLLAMA_NUM_CTX" in str(error.value)


@pytest.mark.parametrize("configured", ["0", "-1"])
def test_a_context_window_that_is_not_positive_is_rejected(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    # No se cae al default: si alguien la bajó para que el modelo entre en
    # memoria, usar 8192 por nuestra cuenta es peor que avisar.
    monkeypatch.setenv("OLLAMA_NUM_CTX", configured)

    with pytest.raises(llm.LLMConfigurationError) as error:
        llm.num_ctx()

    assert "mayor que cero" in str(error.value)


def test_a_broken_context_window_does_not_reach_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_NUM_CTX", "muchísimo")
    client = FakeClient()

    with pytest.raises(llm.LLMConfigurationError):
        llm.run_conversation(
            llm.start_conversation("Hola"),
            tools=[],
            execute_tool=lambda name, arguments: {},
            client=client,
        )

    assert client.calls == []


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
            FakeResponse(FakeMessage(tool_calls=[FakeCall("search_products", {})])),
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
            FakeResponse(FakeMessage(tool_calls=[FakeCall("search_products", {})]))
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
    client = client_with_one_tool_call("search_products", {})

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


def test_a_tool_call_without_a_name_does_not_break_the_turn() -> None:
    # El modelo puede pedir una herramienta sin nombre. No se completa con
    # nada: el router devuelve que no existe y la conversación sigue.
    executed: list[str] = []
    message = llm.run_tool_call(
        FakeCall(None, {}), lambda name, arguments: executed.append(name) or {"found": False}
    )

    assert executed == [""]
    assert message["tool_name"] == ""


def test_a_message_without_tool_calls_has_no_calls() -> None:
    assert llm.tool_calls_of(FakeMessage(content="Hola")) == []


def test_the_default_limit_of_steps_is_low_enough_to_not_hang() -> None:
    assert 1 <= llm.MAX_TOOL_STEPS <= 10
