"""Tests de backend/config_report.py: el reporte de configuración del arranque.

Ningún test lee el `.env` del repo: la fixture `without_the_project_environment`
de `conftest.py` saca esas variables del entorno en todos los tests, y cada uno
pone con `monkeypatch` las que necesita. Así el reporte no depende de cómo tenga
configurada la máquina quien corre los tests.
"""

from __future__ import annotations

import logging

import pytest

from backend import config_report, db, environment, llm

# Las variables que el reporte lee. Son las del proyecto: si alguien agrega una,
# estos tests la cubren sin tocarlos.
REPORTED = environment.PROJECT_VARIABLES

ORIGINS = ["http://localhost:5173"]


# Devuelve la línea del reporte de una variable.
def line_of(variable: str, origins: list[str] | None = None) -> str:
    """Busca en el reporte la línea de una variable.

    Args:
        variable: Nombre de la variable de entorno.
        origins: Orígenes de CORS a reportar. Por defecto `ORIGINS`.

    Returns:
        La línea completa, para poder revisar el valor y la procedencia juntos.
    """
    written = config_report.lines(ORIGINS if origins is None else origins)
    return next(line for line in written if line.strip().startswith(f"{variable} "))


def test_the_report_names_every_setting() -> None:
    written = "\n".join(config_report.lines(ORIGINS))

    for variable in REPORTED:
        assert variable in written


def test_a_configured_value_is_reported_as_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")

    line = line_of("OLLAMA_MODEL")

    assert "llama3.1" in line
    assert config_report.FROM_ENVIRONMENT in line
    assert config_report.FROM_DEFAULT not in line


def test_a_value_that_is_not_configured_is_reported_as_the_default() -> None:
    line = line_of("OLLAMA_MODEL")

    assert llm.DEFAULT_MODEL in line
    assert config_report.FROM_DEFAULT in line


@pytest.mark.parametrize("configured", ["", "   "])
def test_an_empty_variable_counts_as_the_default(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    # Es como la tratan llm.py y db.py: se caen al valor del código.
    monkeypatch.setenv("OLLAMA_MODEL", configured)

    line = line_of("OLLAMA_MODEL")

    assert llm.DEFAULT_MODEL in line
    assert config_report.FROM_DEFAULT in line


def test_the_timeout_is_reported_with_its_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_TIMEOUT", "120")

    line = line_of("OLLAMA_TIMEOUT")

    assert "120 s por llamada" in line
    assert config_report.FROM_ENVIRONMENT in line


def test_an_empty_num_predict_says_that_ollama_decides() -> None:
    # Es el único que no tiene default: sin la variable no se manda la opción.
    line = line_of("OLLAMA_NUM_PREDICT")

    assert "lo decide Ollama" in line
    assert config_report.FROM_DEFAULT in line


def test_a_configured_num_predict_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "400")

    line = line_of("OLLAMA_NUM_PREDICT")

    assert "400 tokens" in line
    assert config_report.FROM_ENVIRONMENT in line


def test_the_cors_origins_are_the_ones_that_were_enabled() -> None:
    # Se reciben resueltos, no se vuelven a leer de la variable: el log tiene
    # que mostrar los que quedaron en el middleware.
    line = line_of("FRONTEND_ORIGINS", ["http://a:1", "http://b:2"])

    assert "http://a:1, http://b:2" in line


def test_the_database_path_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", "otra/base.db")

    line = line_of("DATABASE_PATH")

    # El separador lo escribe Path, que en Windows usa '\': se compara con el
    # mismo str() que usa el reporte para no atarse a una plataforma.
    assert str(db.database_path()) in line
    assert "base.db" in line
    assert config_report.FROM_ENVIRONMENT in line


def test_the_report_names_the_env_file() -> None:
    # Para saber qué archivo se cargó, no solo que hubo uno.
    written = "\n".join(config_report.lines(ORIGINS))

    assert str(environment.ENV_FILE) in written


def test_a_value_that_came_from_the_env_file_is_distinguished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # La distinción sale de environment.py, que anota qué variables entraron al
    # cargar el archivo. Acá se simula ese anotado.
    monkeypatch.setenv("OLLAMA_MODEL", "del-archivo")
    monkeypatch.setattr(environment, "_from_file", frozenset({"OLLAMA_MODEL"}))

    line = line_of("OLLAMA_MODEL")

    assert "del-archivo" in line
    assert config_report.FROM_ENV_FILE in line


@pytest.mark.parametrize(
    "variable",
    [
        "OLLAMA_API_KEY",
        "ollama_api_key",
        "SOME_TOKEN",
        "DB_PASSWORD",
        "CLIENT_SECRET",
        "AUTH_HEADER",
    ],
)
def test_a_variable_that_looks_like_a_secret_is_detected(variable: str) -> None:
    assert config_report.looks_sensitive(variable)


@pytest.mark.parametrize("variable", REPORTED)
def test_none_of_the_reported_variables_looks_like_a_secret(variable: str) -> None:
    # Si alguna empezara a parecerlo, se imprimiría oculta y el reporte dejaría
    # de servir: este test avisa antes de que pase.
    assert not config_report.looks_sensitive(variable)


def test_the_value_of_a_sensitive_variable_is_masked() -> None:
    # La protección principal es la lista explícita, pero si alguien agrega una
    # variable con un secreto, el valor igual no se imprime.
    secret = config_report.Setting("OLLAMA_API_KEY", lambda: "sk-no-imprimir-esto")

    assert config_report.value_of(secret) == config_report.MASKED


def test_a_variable_outside_the_list_is_not_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Lo que se imprime es la lista de SETTINGS, no el entorno: una variable
    # nueva no aparece hasta que alguien la agregue a mano.
    monkeypatch.setenv("OLLAMA_API_KEY", "sk-no-imprimir-esto")
    monkeypatch.setenv("UNA_VARIABLE_CUALQUIERA", "valor")

    written = "\n".join(config_report.lines(ORIGINS))

    assert "sk-no-imprimir-esto" not in written
    assert "UNA_VARIABLE_CUALQUIERA" not in written
    assert "OLLAMA_API_KEY" not in written


def test_a_value_that_cannot_be_resolved_does_not_break_the_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # El reporte es informativo: un valor mal escrito se cuenta en su línea y
    # las demás salen igual. El error de verdad lo levanta quien use la
    # variable, no este log.
    monkeypatch.setenv("OLLAMA_TIMEOUT", "cero")

    line = line_of("OLLAMA_TIMEOUT")

    assert "no se pudo resolver" in line
    assert "OLLAMA_TIMEOUT" in line
    assert llm.DEFAULT_MODEL in line_of("OLLAMA_MODEL")


def test_the_report_is_logged_at_info(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("prueba.config")

    with caplog.at_level(logging.INFO, logger="prueba.config"):
        config_report.log_configuration(logger, frontend_origins=ORIGINS)

    assert caplog.records
    assert caplog.records[0].levelno == logging.INFO
    assert "configuración efectiva" in caplog.text
    assert "OLLAMA_MODEL" in caplog.text


def test_the_report_is_a_single_log_record(caplog: pytest.LogCaptureFixture) -> None:
    # En una sola línea de log para que uvicorn no parta el bloque con las suyas.
    logger = logging.getLogger("prueba.config")

    with caplog.at_level(logging.INFO, logger="prueba.config"):
        config_report.log_configuration(logger, frontend_origins=ORIGINS)

    assert len(caplog.records) == 1
