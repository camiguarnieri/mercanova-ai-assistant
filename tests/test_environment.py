"""Tests de backend/environment.py: la carga del .env y la procedencia.

Ningún test lee el `.env` del repo: cada uno escribe el suyo en `tmp_path`. La
fixture de abajo deja el módulo como si todavía no se hubiera cargado nada, así
que lo que haya en la máquina de quien corre los tests no cambia el resultado.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend import environment


@pytest.fixture(autouse=True)
def forget_the_loaded_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deja el módulo como si `load_env_file()` no se hubiera llamado todavía.

    Importar `backend.api` ya lo llamó una vez, y la carga es idempotente a
    propósito, así que sin esto ningún test podría probar una carga. `monkeypatch`
    devuelve el valor original al terminar.
    """
    monkeypatch.setattr(environment, "_from_file", None)


# Escribe un .env de prueba y devuelve su ruta.
def write_env(tmp_path: Path, content: str) -> Path:
    """Arma un archivo .env para un test.

    Args:
        tmp_path: La carpeta temporal del test.
        content: Las líneas del archivo.

    Returns:
        La ruta del archivo escrito.
    """
    target = tmp_path / ".env"
    target.write_text(content, encoding="utf-8")
    return target


def test_the_env_file_is_looked_up_next_to_the_repository() -> None:
    # La ruta sale de la ubicación del módulo y no del directorio actual: así
    # el .env se encuentra igual desde donde sea que se corra el comando.
    assert environment.ENV_FILE == environment.REPO_ROOT / ".env"
    assert (environment.REPO_ROOT / "backend" / "environment.py").is_file()
    assert (environment.REPO_ROOT / "AGENTS.md").is_file()


def test_the_variables_of_the_file_end_up_in_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    environment.load_env_file(write_env(tmp_path, "OLLAMA_MODEL=del-archivo\n"))

    assert environment.source_of("OLLAMA_MODEL") == environment.FROM_ENV_FILE


def test_the_terminal_wins_over_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # El orden de prioridad correcto: el .env es el valor del proyecto y la
    # terminal es el de esta corrida.
    monkeypatch.setenv("OLLAMA_MODEL", "de-la-terminal")

    environment.load_env_file(write_env(tmp_path, "OLLAMA_MODEL=del-archivo\n"))

    assert os.environ["OLLAMA_MODEL"] == "de-la-terminal"
    assert environment.source_of("OLLAMA_MODEL") == environment.FROM_ENVIRONMENT


def test_a_variable_that_is_not_anywhere_is_the_default_of_the_code(
    tmp_path: Path,
) -> None:
    environment.load_env_file(write_env(tmp_path, "OLLAMA_MODEL=del-archivo\n"))

    assert environment.source_of("OLLAMA_HOST") == environment.FROM_DEFAULT


def test_an_empty_variable_in_the_file_counts_as_the_default(tmp_path: Path) -> None:
    # Así la trata llm.py: OLLAMA_NUM_PREDICT vacío significa que lo decide Ollama.
    environment.load_env_file(write_env(tmp_path, "OLLAMA_NUM_PREDICT=\n"))

    assert environment.source_of("OLLAMA_NUM_PREDICT") == environment.FROM_DEFAULT


def test_without_a_file_nothing_breaks_and_the_defaults_stay(tmp_path: Path) -> None:
    missing = tmp_path / "no-existe" / ".env"

    assert environment.load_env_file(missing) == frozenset()
    assert environment.source_of("OLLAMA_MODEL") == environment.FROM_DEFAULT


def test_the_load_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Sin el resguardo, la segunda llamada vería la variable ya cargada como si
    # viniera de la terminal y el log mentiría sobre su procedencia.
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    env_file = write_env(tmp_path, "OLLAMA_MODEL=del-archivo\n")

    first = environment.load_env_file(env_file)
    second = environment.load_env_file(env_file)

    assert first == second == frozenset({"OLLAMA_MODEL"})
    assert environment.source_of("OLLAMA_MODEL") == environment.FROM_ENV_FILE


def test_what_came_from_the_file_is_empty_before_loading() -> None:
    # Si nadie cargó el archivo, no hay ninguna variable que atribuirle.
    assert environment.loaded_from_file() == frozenset()


def test_the_note_names_the_file_that_was_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Con un archivo propio y no el del repo: que el test pase no puede
    # depender de que esta máquina tenga un .env.
    env_file = write_env(tmp_path, "OLLAMA_MODEL=del-archivo\n")
    monkeypatch.setattr(environment, "ENV_FILE", env_file)

    note = environment.env_file_note()

    assert str(env_file) in note
    assert "le gana" in note


def test_skipping_the_file_makes_the_load_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Es lo que usa conftest.py para que el .env de la máquina no entre en
    # ningún test: el archivo no se lee, ni siquiera si se lo pide.
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    env_file = write_env(tmp_path, "OLLAMA_MODEL=del-archivo\n")

    environment.skip_env_file()

    assert environment.load_env_file(env_file) == frozenset()
    assert os.getenv("OLLAMA_MODEL") is None
    assert environment.source_of("OLLAMA_MODEL") == environment.FROM_DEFAULT


def test_the_note_says_when_there_is_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(environment, "ENV_FILE", Path("/no/existe/.env"))

    note = environment.env_file_note()

    assert "no hay archivo" in note


def test_every_project_variable_is_documented_in_the_example() -> None:
    # Si una variable no está en el .env.example, copiar el archivo y ajustarlo
    # no alcanza para configurarla.
    example = (environment.REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for variable in environment.PROJECT_VARIABLES:
        assert f"{variable}=" in example
