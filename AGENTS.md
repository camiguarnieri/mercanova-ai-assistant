# AGENTS.md — MercaNova AI Shopping Assistant

Reglas del proyecto para cualquier agente de código (Claude Code, Codex, Cursor).
Leer este archivo antes de escribir o modificar código.

---

## 1. Qué es este proyecto

Aplicación de e-commerce con un asistente conversacional. El usuario expresa una
necesidad en lenguaje natural, el asistente le recomienda productos del catálogo real,
responde preguntas y lo acompaña hasta completar una compra ficticia.

Obligatorio 2 de Sistemas de Soporte de Decisión, Universidad ORT Uruguay.

---

## 2. Regla número uno: el modelo no inventa datos

El asistente **nunca** afirma un precio, un stock, una especificación o una marca que no
haya obtenido del backend en esa misma conversación.

- Los datos del catálogo se consultan con *tool calling* contra la base de datos.
- El catálogo **no** se mete dentro del prompt.
- Si una herramienta no devuelve un dato, el asistente dice que no lo tiene. No estima,
  no completa con un valor probable, no usa conocimiento general sobre la marca.
- Antes de afirmar precio o disponibilidad, consultar siempre el estado actual.

Toda sugerencia de código que haga que el modelo "recuerde" datos de producto en vez de
consultarlos está mal y debe rechazarse.

---

## 3. Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.13 + FastAPI |
| Base de datos | SQLite |
| Frontend | React |
| LLM | Ollama local, vía la librería `ollama` |
| Validación | Pydantic v2 |
| Tests | pytest |
| Empaquetado | Docker Compose |

No agregar dependencias nuevas sin justificarlo. Una solución simple y explicable es
preferible a una arquitectura más completa pero difícil de defender.

---

## 4. Organización de archivos

Un archivo, una responsabilidad. Si un archivo pasa de ~150 líneas, partirlo.

```
backend/
  models.py        modelos Pydantic, nada más
  prompts.py       instrucciones para el LLM, como constantes
  llm.py           acceso a Ollama, encapsulado
  tools.py         funciones que el LLM puede invocar
  db.py            acceso a SQLite
  api.py           endpoints FastAPI
tests/
  test_<modulo>.py un archivo por módulo
frontend/
  src/
```

---

## 5. Convenciones de código

- Type hints en todas las funciones: `def buscar(texto: str) -> list[Producto]:`
- Docstring en cada módulo, clase y función pública.
- Un comentario corto en español arriba de cada función, explicando qué hace.
- Nombres de variables y funciones en inglés; comentarios, docstrings y mensajes de
  error en español.
- Los modelos Pydantic usan `ConfigDict(extra="forbid", str_strip_whitespace=True)`.
- Cada campo de un modelo lleva `Field(description=...)`. Esa descripción viaja en el
  JSON Schema que recibe el modelo, así que tiene que estar escrita para que la lea él.

---

## 6. Manejo de errores

Jerarquía de excepciones propia por capa. Los errores se traducen a mensajes que el
usuario puede accionar.

```python
class LLMError(RuntimeError): ...
class LLMConfigurationError(LLMError): ...
class LLMResponseError(LLMError): ...
```

Mal: `raise Exception("error")`
Bien: `raise LLMConfigurationError(f"No se encontró el modelo '{model}'. Instalalo con: ollama pull {model}")`

La aplicación nunca termina abruptamente ni queda en un estado inconsistente.

---

## 7. Testing

**Los tests nunca llaman al modelo ni a la red.** Tienen que correr sin Ollama prendido.

Para probar código que usa el LLM, reemplazar el cliente con un doble y verificar
**lo que se le mandó**, no lo que contestó:

```python
class FakeClient:
    def __init__(self, *, host: str) -> None:
        captured["host"] = host
    def chat(self, **kwargs):
        captured.update(kwargs)
        return FakeResponse(...)

monkeypatch.setattr(llm, "Client", FakeClient)
...
assert captured["format"] == MiModelo.model_json_schema()
assert captured["options"] == {"temperature": 0}
```

Qué cubrir como mínimo:

- validación de los modelos Pydantic (campos obligatorios, valores inválidos, extras);
- las funciones que el LLM puede invocar (tools), con datos de prueba;
- las reglas de negocio: stock insuficiente, carrito vacío, cantidades inválidas;
- los endpoints de la API, con el cliente de test de FastAPI.

Antes de dar una tarea por terminada, correr `pytest` y que pase.

---

## 8. Configuración y secretos

- Todo lo configurable va en variables de entorno.
- `.env.example` se versiona con valores de ejemplo. `.env` nunca se sube.
- Valores por defecto seguros en el código:

```python
model = os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL
host = os.getenv("OLLAMA_HOST") or DEFAULT_HOST
```

Variables del proyecto: `OLLAMA_MODEL`, `OLLAMA_HOST`, `DATABASE_PATH`.

---

## 9. Datos

El catálogo viene de un Excel provisto por la cátedra: 360 productos, 3000
especificaciones, precios, inventario en 5 depósitos, relaciones entre productos,
categorías y marcas.

- La carga del Excel a SQLite es un script aparte y repetible.
- No modificar el Excel original.
- Los datos operativos que invente el equipo (carrito, órdenes) se documentan como tales.

---

## 10. Al trabajar

- Cambios chicos y verificables. Una funcionalidad por vez.
- Explicar en una línea qué hace cada archivo nuevo.
- No crear abstracciones "por las dudas".
- No dejar código comentado ni funciones sin usar.
- Si algo no se puede resolver bien, decirlo en vez de dejar una solución a medias.
- No hacer commits ni push. Dejar los cambios en el working tree; el equipo los revisa y commitea.

El equipo tiene que poder explicar cada decisión en la defensa. Código que funciona pero
que nadie puede explicar no sirve.