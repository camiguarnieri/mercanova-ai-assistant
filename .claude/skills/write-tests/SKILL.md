---
name: write-tests
description: Escribir tests para este proyecto. Usar al agregar funcionalidad nueva, al tocar una tool del asistente o al modificar reglas de negocio.
---

# Escribir tests en MercaNova

## Regla innegociable

**Los tests nunca llaman al modelo ni salen a la red.** Tienen que pasar con Ollama
apagado y sin internet. Si un test necesita que Ollama esté prendido, está mal escrito.

Motivo: un test que depende del modelo es lento, cuesta plata en tiempo y falla distinto
cada vez. No prueba el código, prueba al modelo.

## Cómo probar código que usa el LLM

Reemplazar el cliente por un doble y verificar **qué se le mandó**, no qué contestó.

```python
import pytest
import llm
from models import ProductRequirements


def test_returns_the_typed_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = ProductRequirements(category="monitor", max_price=500)
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, host: str) -> None:
            captured["host"] = host

        def chat(self, **kwargs: object) -> object:
            captured.update(kwargs)
            message = type("FakeMessage", (), {"content": expected.model_dump_json()})()
            return type("FakeResponse", (), {"message": message})()

    monkeypatch.setattr(llm, "Client", FakeClient)
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")

    result = llm.extract_product_requirements("Quiero un monitor de menos de 500")

    assert result == expected
    assert captured["model"] == "test-model"
    assert captured["options"] == {"temperature": 0}
```

Lo que se verifica: que se usó el modelo configurado, que la temperatura es 0, que se
mandó el schema correcto y que la respuesta se validó con Pydantic.

## Qué cubrir en cada capa

**Modelos Pydantic**
- campos obligatorios ausentes;
- valores inválidos (precio negativo, cantidad cero);
- campos extra, que tienen que ser rechazados por `extra="forbid"`;
- normalización (espacios, mayúsculas).

**Tools del asistente**
- resultado correcto con datos de prueba;
- producto inexistente;
- búsqueda sin resultados;
- que nunca devuelvan datos que no estén en la base.

**Reglas de negocio**
- comprar más unidades de las disponibles;
- comprar un producto sin stock;
- checkout con el carrito vacío;
- cantidad cero o negativa;
- que el stock baje después de confirmar una compra.

**Endpoints**
- usar `TestClient` de FastAPI;
- código de estado y forma de la respuesta;
- qué pasa con un id que no existe.

## Convenciones

- Un archivo `test_<modulo>.py` por cada módulo.
- Nombre del test en inglés y que describa el comportamiento esperado:
  `test_rejects_quantity_above_available_stock`, no `test_stock_2`.
- Un concepto por test. Si el nombre necesita un "y", son dos tests.
- Usar `@pytest.mark.parametrize` para varios casos de la misma regla.
- Datos de prueba creados en el test, nunca leídos de la base real.

## Antes de terminar

Correr `pytest` y que pase todo. Si un test falla, arreglar el código o el test, nunca
borrarlo ni marcarlo para saltear.