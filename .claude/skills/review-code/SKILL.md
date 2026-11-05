---
name: review-code
description: Revisar código antes de mergear un pull request. Usar sobre cualquier cambio generado por un agente antes de incorporarlo a main.
---

# Revisar código en MercaNova

Revisar contra las reglas de `AGENTS.md`. Reportar solo lo que está mal, con el archivo
y la línea. No reescribir el código sin que se lo pidan.

## 1. Invención de datos — lo más grave

- ¿El asistente afirma precio, stock o especificación sin haberlo consultado?
- ¿Hay datos del catálogo metidos dentro de un prompt en vez de consultarse con tools?
- ¿Alguna tool devuelve un valor por defecto inventado cuando no encuentra nada?
- ¿El prompt le permite al modelo "completar" información faltante?

Cualquiera de estas rompe el RF-18 y es motivo de rechazo del cambio.

## 2. Secretos y configuración

- ¿Hay alguna URL, clave o ruta escrita directo en el código?
- ¿Lo configurable sale de variables de entorno con un valor por defecto seguro?
- ¿Las variables nuevas están documentadas en `.env.example`?
- ¿Algún `.env` quedó fuera del `.gitignore`?

## 3. Manejo de errores

- ¿Hay `except:` o `except Exception:` sin tipo específico?
- ¿Algún error se traga en silencio?
- ¿Los mensajes dicen qué pasó y qué hacer, o solo "error"?
- Si falla a mitad de una operación, ¿el estado queda consistente?

## 4. Estructura

- ¿Algún archivo pasa de 150 líneas?
- ¿Cada archivo tiene una sola responsabilidad?
- ¿Hay lógica de negocio mezclada con endpoints o con acceso a la base?
- ¿Quedó código comentado, funciones sin usar o imports de más?

## 5. Convenciones

- ¿Type hints en todas las funciones?
- ¿Docstring en los módulos y funciones públicas?
- ¿Nombres en inglés, comentarios y mensajes en español?
- ¿Los modelos Pydantic usan `extra="forbid"` y `Field(description=...)`?

## 6. Tests

- ¿El cambio trae tests?
- ¿Algún test necesita Ollama prendido o acceso a la red?
- ¿Se probaron los casos de error, no solo el camino feliz?
- ¿Pasa `pytest`?

## 7. La pregunta final

¿Podría explicar este código en la defensa sin dudar?

Si la respuesta es no, el problema no es el revisor: el código es más complicado de lo
que el problema necesita. Pedir que se simplifique.

## Formato del reporte

Agrupar por gravedad:

- **Bloqueante** — invención de datos, secreto en el código, test que llama al modelo.
- **Importante** — error mal manejado, archivo gigante, falta de tests.
- **Menor** — convención de nombres, docstring faltante.

Para cada hallazgo: archivo, línea, qué está mal y qué se espera en su lugar.