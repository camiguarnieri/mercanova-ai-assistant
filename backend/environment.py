"""Carga del `.env` y de dónde salió cada variable de configuración.

El `.env.example` dice "copiar a .env y ajustar", así que el `.env` tiene que
tener efecto. Lo carga `load_env_file()`, que llaman los puntos de entrada: la
aplicación en `api.py` y los scripts que leen configuración.

**Una variable puesta en la terminal le gana a la del `.env`.** Es el
comportamiento de `load_dotenv()` sin `override`, y es el orden correcto: el
`.env` es el valor del proyecto y la terminal es el de esta corrida.

Mientras carga, se anota qué variables entraron desde el archivo. Eso es lo que
después le permite al log de arranque decir "del .env" o "del entorno del
proceso" en vez de un "configurado" que no distingue nada: la diferencia se
puede saber porque el anotado se hace **antes** de cargar, en el mismo proceso.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

__all__ = [
    "ENV_FILE",
    "FROM_DEFAULT",
    "FROM_ENVIRONMENT",
    "FROM_ENV_FILE",
    "PROJECT_VARIABLES",
    "REPO_ROOT",
    "env_file_note",
    "load_env_file",
    "loaded_from_file",
    "skip_env_file",
    "source_of",
]

# La raíz del repositorio, deducida de la ubicación de este archivo y no del
# directorio desde el que se corrió el comando: así el `.env` se encuentra igual
# si se arranca desde la raíz, desde `backend/` o desde cualquier otra carpeta.
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"

# Las variables que configuran este proyecto. Es también la lista que los tests
# limpian del entorno, para que no los afecte el `.env` de cada máquina.
PROJECT_VARIABLES = (
    "OLLAMA_MODEL",
    "OLLAMA_HOST",
    "OLLAMA_TIMEOUT",
    "OLLAMA_NUM_CTX",
    "OLLAMA_NUM_PREDICT",
    "OLLAMA_KEEP_ALIVE",
    "DATABASE_PATH",
    "FRONTEND_ORIGINS",
)

# De dónde puede salir un valor, como se escribe en el log de arranque.
FROM_ENV_FILE = "del .env"
FROM_ENVIRONMENT = "del entorno del proceso"
FROM_DEFAULT = "default del código"

# Qué variables entraron desde el archivo. `None` significa que todavía no se
# cargó, que no es lo mismo que haber cargado un archivo sin variables nuevas.
_from_file: frozenset[str] | None = None


# Carga el .env de la raíz del repo, sin pisar lo que ya esté en el entorno.
def load_env_file(path: Path | None = None) -> frozenset[str]:
    """Mete en el entorno las variables del `.env`.

    Es idempotente: la primera llamada carga y anota, y las siguientes
    devuelven lo mismo sin volver a mirar el entorno. Sin ese resguardo, la
    segunda llamada vería las variables ya cargadas como si hubieran venido de
    la terminal y el log de arranque mentiría sobre su procedencia.

    Args:
        path: Archivo a cargar. Si es `None` se usa `ENV_FILE`.

    Returns:
        Los nombres de las variables que entraron desde el archivo. Vacío si no
        hay archivo —en ese caso no se toca nada y todo sigue andando con los
        defaults del código— o si todas ya estaban en el entorno.
    """
    global _from_file
    if _from_file is not None:
        return _from_file
    before = set(os.environ)
    # Sin `override`: lo que ya está en el entorno le gana al archivo.
    load_dotenv(ENV_FILE if path is None else Path(path))
    _from_file = frozenset(name for name in os.environ if name not in before)
    return _from_file


# Da la carga por hecha sin leer el archivo, para que los tests no lo vean.
def skip_env_file() -> None:
    """Marca el `.env` como ya cargado, sin leerlo.

    La llama `tests/conftest.py` antes de importar `backend.api`, que carga el
    archivo al importarse. Con esto la carga queda en no-op y **el `.env` de la
    máquina no se lee en ningún test**.

    Hace falta porque no alcanza con sacar las variables del entorno en cada
    test: los orígenes de CORS se resuelven cuando se arma el middleware, que
    es al importar el módulo, así que un `FRONTEND_ORIGINS` del archivo quedaría
    fijado en la aplicación antes de que corra la primera fixture.

    Usa el mismo resguardo que hace idempotente a `load_env_file()`: dejar
    anotado que ya se cargó, con ninguna variable venida del archivo.
    """
    global _from_file
    _from_file = frozenset()


# Devuelve qué variables entraron desde el archivo, sin cargarlo.
def loaded_from_file() -> frozenset[str]:
    """Trae lo que anotó `load_env_file()`.

    Returns:
        Los nombres que entraron desde el `.env`, o un conjunto vacío si
        todavía no se cargó. Vacío a propósito en ese caso: si nadie cargó el
        archivo, no hay ninguna variable que se le pueda atribuir.
    """
    return frozenset() if _from_file is None else _from_file


# Dice si el valor salió del .env, del entorno del proceso o del código.
def source_of(variable: str) -> str:
    """Resuelve de dónde salió el valor de una variable.

    Args:
        variable: Nombre de la variable de entorno.

    Returns:
        `FROM_DEFAULT` si no está en el entorno o está vacía —así la tratan
        `llm.py` y `db.py`, que se caen al valor del código—, `FROM_ENV_FILE`
        si la puso la carga del archivo, y `FROM_ENVIRONMENT` si ya estaba
        antes. Lo último incluye la terminal, el perfil de la shell y un `-e`
        de Docker: para el proceso son todos lo mismo, y por eso no se nombra
        solo la terminal.
    """
    if not (os.getenv(variable) or "").strip():
        return FROM_DEFAULT
    return FROM_ENV_FILE if variable in loaded_from_file() else FROM_ENVIRONMENT


# Escribe, para el log, qué pasó con el archivo .env.
def env_file_note() -> str:
    """Describe de qué archivo salieron las variables, si hubo uno.

    Returns:
        La ruta del `.env` y la aclaración de que la terminal le gana, o que no
        hay archivo y los valores salen del entorno o del código.
    """
    if ENV_FILE.is_file():
        return (
            f".env: {ENV_FILE} (una variable puesta en la terminal le gana a la del "
            f"archivo)"
        )
    return f".env: no hay archivo en {ENV_FILE}, así que se usan el entorno y los defaults"
