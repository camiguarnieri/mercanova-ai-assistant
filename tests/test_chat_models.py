"""Tests de backend/chat_models.py: el contrato de entrada y salida del chat."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.chat_models import (
    MAX_MESSAGE_LENGTH,
    AssistantTurn,
    ChatRequest,
    ChatResponse,
    ToolInvocation,
)


def test_a_request_needs_the_session_and_the_message() -> None:
    request = ChatRequest(session_id="s-1", message="Quiero un monitor")

    assert request.session_id == "s-1"
    assert request.message == "Quiero un monitor"


@pytest.mark.parametrize("missing", ["session_id", "message"])
def test_a_request_without_a_required_field_is_rejected(missing: str) -> None:
    fields = {"session_id": "s-1", "message": "Hola"}
    del fields[missing]

    with pytest.raises(ValidationError):
        ChatRequest(**fields)


def test_a_request_trims_the_message() -> None:
    request = ChatRequest(session_id="s-1", message="  Quiero un monitor  ")

    assert request.message == "Quiero un monitor"


@pytest.mark.parametrize("message", ["", "   ", "\n"])
def test_an_empty_message_is_rejected(message: str) -> None:
    # Un mensaje de solo espacios queda vacío al limpiarlo: no hay qué contestar.
    with pytest.raises(ValidationError):
        ChatRequest(session_id="s-1", message=message)


@pytest.mark.parametrize("session_id", ["", "   "])
def test_an_empty_session_is_rejected(session_id: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(session_id=session_id, message="Hola")


def test_a_message_longer_than_the_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(session_id="s-1", message="a" * (MAX_MESSAGE_LENGTH + 1))


def test_a_request_with_an_extra_field_is_rejected() -> None:
    # El cliente no manda el historial: lo guarda el servidor.
    with pytest.raises(ValidationError):
        ChatRequest(session_id="s-1", message="Hola", history=[])


def test_an_invocation_keeps_its_arguments() -> None:
    invocation = ToolInvocation(
        name="search_products", arguments={"category": "Headphones", "max_price": 200}
    )

    assert invocation.arguments == {"category": "Headphones", "max_price": 200}


def test_an_invocation_without_arguments_has_an_empty_dictionary() -> None:
    # Una búsqueda sin filtros no lleva argumentos y se muestra igual.
    assert ToolInvocation(name="search_products").arguments == {}


def test_an_invocation_without_a_name_is_accepted() -> None:
    # El modelo puede pedir una herramienta sin nombre: tiene que llegar hasta
    # la interfaz, que no la muestra, en vez de cortar el turno con un error.
    assert ToolInvocation(name="").name == ""


def test_a_turn_without_tools_reports_an_empty_list() -> None:
    # Vacío significa "no consultó nada", no "no se sabe".
    assert AssistantTurn(reply="¿Para qué lo vas a usar?").tools_used == []


def test_a_turn_lists_the_tools_in_order() -> None:
    turn = AssistantTurn(
        reply="Te recomiendo ese.",
        tools_used=[
            ToolInvocation(name="search_products", arguments={"category": "Monitors"}),
            ToolInvocation(name="check_availability", arguments={"product_id": "MN-MON-0001"}),
        ],
    )

    assert [tool.name for tool in turn.tools_used] == ["search_products", "check_availability"]


def test_a_response_carries_the_session() -> None:
    response = ChatResponse(session_id="s-1", reply="Hola")

    assert response.session_id == "s-1"
    assert response.tools_used == []


def test_a_response_with_an_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatResponse(session_id="s-1", reply="Hola", total=3)
