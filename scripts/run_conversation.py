"""Corre una conversación de prueba contra Ollama y el catálogo real.

No es un test: los tests no llaman al modelo. Esto es la corrida manual que se
usa para revisar una ronda de cambios y para grabar el video. Cada turno
imprime lo que contestó el modelo, qué herramientas se ejecutaron con qué
argumentos, lo que la interfaz va a imprimir como dato, cuánto tardó y cuánto
ocupa el historial que viaja al modelo.

    python -m scripts.run_conversation

Necesita Ollama prendido con el modelo de OLLAMA_MODEL y la base cargada.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time

from fastapi.testclient import TestClient

from backend import api, llm, sessions

# La sesión de la corrida. Se usa también para leer el historial guardado y
# medir cuánto ocupa en la ventana de contexto.
SESSION = "corrida"

# Los siete turnos que repetimos cada ronda. Cada uno reproduce una falla
# reportada, y van en una sola sesión para que el contexto se acumule como en
# una conversación real.
TURNS = [
    ("saludo, no tiene que consultar nada", "hola"),
    ("solo una categoría: tiene que preguntar antes de buscar", "quiero una notebook"),
    ("ahora sí hay con qué buscar", "para programar, hasta 1500 dólares"),
    ("RF-07: el número de stock sale de check_availability", "¿hay stock del primero?"),
    ("paso determinístico de nombres", "¿tenés el Aether Dock Hub 7?"),
    (
        "multi-paso: 'video calls' no existe en Headphones",
        "quiero auriculares para videollamadas, menos de 200 dólares",
    ),
    ("compare_products con los cinco que mostró", "¿cuál de esos tiene mejor batería?"),
]

# Lo que el texto del modelo no tiene que nombrar: son datos que imprime la
# interfaz. Es una revisión mecánica, no una prueba: señala para dónde mirar.
PRICE = re.compile(r"\d+[.,]\d{2}|\bUSD\b|\$\s?\d")
SPEC_VALUE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:h|hs|horas|mm|in|Hz|W|GB|TB)\b", re.IGNORECASE)


# Escribe una línea de la corrida.
def say(text: str = "") -> None:
    """Imprime y vacía el buffer, para poder seguir la corrida en vivo."""
    print(text, flush=True)


# Mide un historial con la misma aproximación que el tope del prompt.
def tokens(messages: list[dict]) -> int:
    """Estima en tokens lo que ocupa una lista de mensajes.

    Se aproxima como `len/4`, que es la medida con la que se viene comparando el
    tamaño del prompt en `tests/test_prompts.py`.

    Args:
        messages: Los mensajes, en el formato de Ollama.

    Returns:
        La cantidad estimada de tokens.
    """
    return len(json.dumps(messages, ensure_ascii=False, default=str)) // 4


# Revisa si el texto del modelo nombra un valor del catálogo.
def prose_warnings(reply: str) -> list[str]:
    """Busca en la respuesta los valores que ya imprime la interfaz.

    Args:
        reply: El texto que escribió el modelo.

    Returns:
        Las advertencias encontradas, vacío si el texto no nombra ningún valor.
    """
    warnings = []
    if PRICE.search(reply):
        warnings.append(f"nombra un precio: {PRICE.findall(reply)}")
    if SPEC_VALUE.search(reply):
        warnings.append(f"nombra una especificación: {SPEC_VALUE.findall(reply)}")
    if "MN-" in reply:
        warnings.append("muestra un product_id, que es interno")
    return warnings


# Corre los siete turnos en una sesión y los imprime.
def main() -> int:
    """Corre la conversación completa.

    Returns:
        0 si todos los turnos contestaron, 1 si alguno falló.
    """
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    say(
        f"modelo: {llm.model_name()} | host: {llm.host()} | num_ctx: {llm.num_ctx()} | "
        f"num_predict: {llm.num_predict()} | keep_alive: {llm.keep_alive()}"
    )

    started = time.monotonic()
    llm.preload_model()
    say(f"precarga: {time.monotonic() - started:.1f}s")

    failed = 0
    with TestClient(api.app) as client:
        for number, (what, message) in enumerate(TURNS, start=1):
            say("\n" + "=" * 78)
            say(f"TURNO {number} — {what}")
            say(f"usuario: {message}")
            turn_started = time.monotonic()
            response = client.post(
                "/chat", json={"session_id": SESSION, "message": message}
            )
            elapsed = time.monotonic() - turn_started

            if response.status_code != 200:
                failed += 1
                say(f"ERROR {response.status_code}: {response.json().get('detail')}")
                continue

            body = response.json()
            say(f"\nasistente ({elapsed:.1f}s): {body['reply']}")

            say("\nherramientas:")
            if not body["tools_used"]:
                say("   (ninguna)")
            for tool in body["tools_used"]:
                arguments = ", ".join(f"{k}={v!r}" for k, v in tool["arguments"].items())
                say(f"   {tool['name']}({arguments})")

            if body["products"]:
                say("\ntarjetas que imprime la interfaz:")
                for product in body["products"]:
                    say(
                        f"   {product['product_id']}  {product['name']}  "
                        f"{product['currency']} {product['current_price']}  "
                        f"in_stock={product['in_stock']}"
                    )
            for comparison in body["comparisons"]:
                order = [product["product_id"] for product in comparison["products"]]
                names = " | ".join(product["name"] for product in comparison["products"])
                say(f"\ntabla que imprime la interfaz: {names}")
                for specification in comparison["specifications"]:
                    # Cada celda trae el nombre del producto además del valor:
                    # acá se imprime solo el valor, porque el encabezado ya
                    # dice de quién es cada columna.
                    cells = " | ".join(
                        specification["values"].get(product_id, {}).get("value", "sin dato")
                        for product_id in order
                    )
                    say(f"   {specification['attribute_name']}: {cells}")

            # Cuánto ocupa el historial que viaja al modelo. El prompt del
            # sistema y los esquemas suman unos 2800 más, sobre 8192.
            stored = sessions.STORE.history(SESSION) or []
            say(f"\nhistorial: {tokens(stored)} tokens")

            warnings = prose_warnings(body["reply"])
            if warnings:
                say("\nrevisar el texto:")
                for warning in warnings:
                    say(f"   {warning}")

    say("\n" + "=" * 78)
    say(f"turnos con error: {failed} de {len(TURNS)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
