"""Reporte de la configuración efectiva, para el log de arranque.

Existe para contestar de un vistazo "¿con qué está corriendo esto?" sin tener
que cruzar el `.env`, las variables del entorno y los defaults del código.

**Qué se imprime es una lista explícita, no todo el entorno.** `SETTINGS` nombra
una por una las variables que se reportan y cómo se lee cada valor: una variable
nueva no aparece en el log hasta que alguien la agregue acá a mano. Eso es a
propósito, y es lo que hace que un secreto no se pueda filtrar por descuido.

No resuelve configuración propia: cada valor se lee de donde ya se resolvía
—`llm.py`, `db.py`— así que el log no puede mostrar un número distinto del que
usa la aplicación.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from backend import db, environment, llm
from backend.environment import (
    FROM_DEFAULT,
    FROM_ENVIRONMENT,
    FROM_ENV_FILE,
    source_of,
)

__all__ = [
    "FROM_DEFAULT",
    "FROM_ENVIRONMENT",
    "FROM_ENV_FILE",
    "MASKED",
    "SENSITIVE_HINTS",
    "Setting",
    "looks_sensitive",
    "source_of",
    "value_of",
    "settings",
    "lines",
    "log_configuration",
]

# Lo que se imprime en lugar del valor de una variable que parece un secreto.
MASKED = "*** (oculto)"

# Segunda red, por si alguien agrega a `SETTINGS` una variable con un secreto:
# si el nombre tiene alguna de estas partes, se imprime `MASKED` en vez del
# valor. No es la protección principal —esa es la lista explícita— pero un
# descuido es más probable que un ataque, y esto lo cubre.
#
# No es hipotético: la librería `ollama` ya lee `OLLAMA_API_KEY` del entorno por
# su cuenta, así que una variable con un secreto en este proyecto es plausible.
SENSITIVE_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH")

# De dónde sale cada valor y cómo se dice si vino del entorno o del archivo lo
# resuelve `environment.py`, que es el que carga el `.env` y por eso es el único
# que puede distinguirlos.


@dataclass(frozen=True)
class Setting:
    """Una variable de configuración que se reporta en el log de arranque.

    Attributes:
        variable: Nombre de la variable de entorno, tal como se escribe en el
            `.env`. Es también lo que se busca en `os.environ` para decir si el
            valor vino configurado o es el default del código.
        read: Cómo se lee el valor efectivo, ya escrito para que lo lea una
            persona. Llama a la misma función que usa la aplicación, así el log
            no puede decir un número distinto del que se está usando.
    """

    variable: str
    read: Callable[[], str]


# Escribe el valor de num_predict, que puede no tener ninguno.
def predict_limit() -> str:
    """Describe el tope de tokens de la respuesta.

    Returns:
        El tope configurado, o la aclaración de que no hay uno propio y lo
        decide Ollama, que es lo que pasa cuando la variable está vacía.
    """
    limit = llm.num_predict()
    return "sin tope propio: lo decide Ollama" if limit is None else f"{limit} tokens"


# Dice si el nombre de una variable sugiere que su valor es un secreto.
def looks_sensitive(variable: str) -> bool:
    """Decide si el valor de una variable no se puede imprimir.

    Args:
        variable: Nombre de la variable de entorno.

    Returns:
        `True` si el nombre tiene alguna de las partes de `SENSITIVE_HINTS`,
        sin importar mayúsculas.
    """
    name = variable.upper()
    return any(hint in name for hint in SENSITIVE_HINTS)


# Lee el valor de una variable sin dejar que un error corte el arranque.
def value_of(setting: Setting) -> str:
    """Resuelve el valor efectivo de una variable, ya escrito.

    Args:
        setting: La variable a leer.

    Returns:
        El valor, `MASKED` si el nombre parece de un secreto, o el motivo por el
        que no se pudo resolver. Un valor mal escrito —`OLLAMA_TIMEOUT=cero`—
        hace que su propia función levante `LLMConfigurationError`: eso se
        reporta en la línea y el arranque sigue, porque este log es informativo
        y no puede ser el que tire la aplicación. El error de verdad lo levanta
        después quien use la variable.
    """
    if looks_sensitive(setting.variable):
        return MASKED
    try:
        return setting.read()
    except Exception as error:  # noqa: BLE001 - el log nunca rompe el arranque
        return f"no se pudo resolver: {error}"


# Las variables que se reportan, en el orden en que se imprimen.
def settings(frontend_origins: list[str]) -> list[Setting]:
    """Arma la lista de variables a reportar.

    Los orígenes de CORS se reciben en vez de resolverse acá: los resuelve
    `api.py`, que es el que arma el middleware, así el log muestra los mismos
    que quedaron habilitados y no una segunda lectura de la variable.

    Args:
        frontend_origins: Los orígenes que quedaron habilitados para CORS.

    Returns:
        Las variables, cada una con cómo leer su valor.
    """
    return [
        Setting("OLLAMA_MODEL", llm.model_name),
        Setting("OLLAMA_HOST", llm.host),
        Setting("OLLAMA_TIMEOUT", lambda: f"{llm.timeout_seconds():g} s por llamada"),
        Setting("OLLAMA_NUM_CTX", lambda: f"{llm.num_ctx()} tokens"),
        Setting("OLLAMA_NUM_PREDICT", predict_limit),
        Setting("OLLAMA_KEEP_ALIVE", llm.keep_alive),
        Setting("DATABASE_PATH", lambda: str(db.database_path())),
        Setting("FRONTEND_ORIGINS", lambda: ", ".join(frontend_origins)),
    ]


# Arma las líneas del reporte, alineadas para poder leerlas de un vistazo.
def lines(frontend_origins: list[str]) -> list[str]:
    """Escribe el reporte de la configuración efectiva.

    Args:
        frontend_origins: Los orígenes que quedaron habilitados para CORS.

    Returns:
        Una línea por variable, con el nombre, el valor y de dónde salió, más
        la línea del `.env` al final: qué archivo se cargó, o que no hay.
    """
    reported = settings(frontend_origins)
    width = max(len(setting.variable) for setting in reported)
    written = [
        f"  {setting.variable:<{width}} = {value_of(setting)} ({source_of(setting.variable)})"
        for setting in reported
    ]
    return [*written, f"  {environment.env_file_note()}"]


# Deja la configuración efectiva en el log, antes de cualquier otra precarga.
def log_configuration(logger: logging.Logger, *, frontend_origins: list[str]) -> None:
    """Loguea la configuración con la que quedó corriendo la aplicación.

    Va en una sola llamada y no una por variable: el log de uvicorn intercala
    sus propias líneas, y así el bloque no se parte.

    Args:
        logger: Dónde escribir. Lo pasa quien llama para que la línea salga con
            el nombre de su módulo.
        frontend_origins: Los orígenes que quedaron habilitados para CORS.
    """
    logger.info("configuración efectiva:\n%s", "\n".join(lines(frontend_origins)))
