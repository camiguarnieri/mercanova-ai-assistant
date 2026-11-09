# Caso reproducible de tool calling multi-paso

Para el diagrama de secuencia y el video. El modelo manda un filtro inválido, la
herramienta le devuelve los valores válidos y corrige en el paso siguiente.

## Qué escribir en el chat

```
quiero auriculares para videollamadas, menos de 200 dólares
```

Con la sesión limpia (botón de recargar la página, o borrar
`mercanova.session_id` del localStorage), para que no haya contexto anterior.

## Por qué este mensaje

"Videollamadas" tiene una traducción obvia al inglés del catálogo —`video
calls`— y **ese valor existe**, pero solo en Webcams: los auriculares usan
`calls`. El modelo lo toma del `enum` global de `recommended_for`, que es
global a propósito para validar, y combina dos valores que por separado son
válidos. El error no depende de que el modelo se equivoque en algo raro: la
pista que lo lleva al valor equivocado está en el esquema.

## La traza, verificada contra `data/mercanova.db`

**Paso 1** — el modelo invoca:

```
search_products(category='Headphones', recommended_for='video calls', max_price=200)
```

La herramienta no busca: `search_filters.filter_problems()` detecta que la
combinación no existe y devuelve

> No se puede buscar con esos filtros. La categoría 'Headphones' no tiene
> productos para 'video calls'. Sus casos de uso son: calls, commuting, music,
> sports, travel. Usá uno de esos, o buscá sin recommended_for y mirá el campo
> recommended_for de cada resultado. Corregí lo que esté mal y buscá de nuevo.

**Paso 2** — el modelo corrige y vuelve a invocar:

```
search_products(category='Headphones', recommended_for='calls', max_price=200)
```

```
found=True, 5 de 24
MN-HDP-0001  Aether Sound 880     USD 182.94  in_stock=True  music; calls; commuting; travel; sports
MN-HDP-0009  EchoPeak Pulse 309   USD 165.82  in_stock=True  music; calls; commuting; sports
MN-HDP-0012  Flux Pulse 749       USD  29.18  in_stock=True  music; calls; commuting
```

**Paso 3** — el modelo responde en texto, y la interfaz imprime las tarjetas con
el precio, el stock y los usos de cada producto.

En la traza plegable de la respuesta se ven las dos invocaciones, con sus
argumentos: es la evidencia del RF-18 y de que el segundo intento corrigió el
primero.

## Qué es determinístico y qué no

- **Determinístico**: todo lo del lado del sistema. Dado el paso 1, el mensaje
  de error es siempre ese, con esos cinco casos de uso, y el paso 2 devuelve
  siempre esos productos. Está cubierto por
  `tests/test_search_filters.py::test_a_use_case_that_does_not_exist_in_that_category_is_a_problem`
  y por `tests/test_tool_router.py::test_an_invented_use_case_comes_back_with_the_valid_ones`.
- **No determinístico**: que el modelo elija `video calls` en el paso 1. Es lo
  que hicieron las dos versiones que probamos, pero es una decisión del modelo.
  Si en la grabación corrige de entrada y no se ve el paso 1, estas dos variantes
  fuerzan el mismo camino:
  - `busco auriculares para hacer videoconferencias por menos de 200`
  - `auriculares para reuniones de Zoom, hasta 200 dólares`

  Y si ninguna lo logra, el mismo mecanismo se ve con un filtro que no existe en
  ninguna categoría: `quiero un monitor para edición de audio` (`audio editing`
  no está en el catálogo; `video editing` sí).

## Otro caso, por si hace falta uno más corto

```
¿tenés el Aether Dock Hub 7?
```

No es multi-paso del modelo, pero muestra el paso determinístico de nombres:
antes de que el modelo decida, el sistema busca el nombre en SQLite e inyecta
el resultado (MN-DOC-0029, USD 352.59, sin stock). En la traza aparece como
"El sistema buscó en el catálogo el nombre que escribiste".
