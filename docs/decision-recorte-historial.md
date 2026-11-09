# Decisión de diseño: recortar el historial de la conversación

**Estado: implementado, medido y revertido.** Hoy la conversación le viaja entera
al modelo, como antes. El recorte no quedó en el código.

Este documento se conserva porque el resultado fue negativo y la medición es la
que lo muestra. El desenlace está al final, en "Qué pasó". Lo que sigue es el
razonamiento con el que se tomó la decisión, en el orden en que se tomó.

El punto de Limitaciones sobre las conversaciones largas **sigue en pie**: no lo
reemplaza nada.

## El problema

La conversación de una sesión se le mandaba entera al modelo en cada turno, con
los resultados de todas las herramientas que se habían ejecutado. Eso trae dos
problemas distintos, y el segundo es el importante.

**Tiempo.** El modelo corre en CPU con `num_ctx` en 8192. El prompt del sistema
más los esquemas de las cinco herramientas ocupan unos 2800 tokens fijos por
turno, así que lo que queda para la conversación son unos 5400. Medido sobre la
corrida de siete turnos de `scripts/run_conversation.py`, el historial del turno
7 ocupa 2767 tokens: el pedido completo queda en unos 5567, el 68% de la
ventana. Cada turno reprocesa todo eso.

**Datos vencidos (RF-07).** Los resultados viejos de herramientas son de donde
el modelo saca los datos que ya no valen. El "7 unidades disponibles" que en una
corrida anterior le puso a dos productos distintos salió del historial, no de una
consulta: el resultado de un `check_availability` de tres turnos antes seguía a
mano y lo reusó. Mientras el resultado esté en el contexto, pedirle en el prompt
que vuelva a consultar compite con un dato que tiene delante. Si el resultado no
está, no hay con qué contestar sin consultar.

Esta segunda razón es la que hace que el recorte sea una regla de negocio y no
una optimización.

## Alternativas consideradas

### 1. No recortar

Es lo que había. Se descarta por las dos razones de arriba. El argumento a favor
era que el modelo conserva todo el detalle de la conversación, pero en la
práctica el detalle que conserva incluye precios y stocks vencidos, que es
exactamente lo que no queremos que conserve.

### 2. Recortar por cantidad de turnos, borrando los mensajes viejos

Se conservan completos los últimos N turnos del usuario. De ahí hacia atrás queda
el texto de la conversación y se **borran** los mensajes con rol `tool` y los
pedidos de herramienta que les correspondían.

Fue la primera implementación y **se descarta por medición**. Con ella, en la
corrida de siete turnos el modelo dejó de llamar herramientas en los turnos 6 y 7
e inventó tres productos que no existen en el catálogo (`NovaTech Headset Pro
2`, `3` y `4`, los tres a $199.99), con precio y stock inventados. Con el
historial entero, en la misma corrida y con el mismo código, llamó
`search_products` en el turno 6 y `compare_products` en el 7.

La explicación es que al borrar los mensajes se borra también la constancia de
que en esta conversación se consultó el catálogo, que es el ejemplo que el
modelo venía imitando. Es el mismo modo de falla que ya habíamos visto con el
prompt de 1164 tokens: un modelo de 3B deja de llamar herramientas cuando se le
saca el patrón de adelante. Arreglar la causa en el prompt no era una opción:
esa versión quedó fijada en 879 tokens.

### 3. Recortar por cantidad de turnos, vaciando los resultados viejos — **la que se implementó**

Igual que la anterior, pero los mensajes de los turnos viejos **no se borran**:
queda la forma de la conversación completa —las preguntas, las respuestas y los
pedidos de herramienta con sus argumentos— y lo único que se reemplaza es el
*contenido* de cada resultado, por la frase de `history.DISCARDED_RESULT`, que
dice que ese dato se descartó y que hay que volver a consultarlo. El prompt del
sistema queda siempre.

A favor: saca el dato vencido, que es el objetivo, y deja el ejemplo de uso de
herramientas, que es lo que se había roto con la alternativa 2. La unidad de
recorte coincide además
con la unidad de referencia del usuario: "¿hay stock del primero?" y "¿cuál de
esos tiene mejor batería?" se refieren al resultado del turno anterior, no a un
rango de tokens. Es explicable en una línea y se prueba sin el modelo.

En contra: ahorra menos que borrar los mensajes, porque los pedidos de
herramienta con sus argumentos y la frase de reemplazo siguen ocupando lugar. Y
un turno con una búsqueda de cinco productos pesa mucho más que un "gracias",
así que N turnos no es una cantidad fija de tokens.

### 4. Recortar por tokens

Ir sacando mensajes viejos hasta que el historial baje de un presupuesto, por
ejemplo 3000 tokens.

Se descarta: controla mejor el peor caso, pero corta por un lugar que no tiene
sentido para la conversación. Puede dejar un resultado de herramienta sin el
pedido que lo originó, o cortar un turno al medio, y el modelo se queda con la
mitad de un intercambio. Además obliga a contar tokens, y lo único que tenemos
es la aproximación `len/4` que usamos para el prompt: tomar una decisión de
corte con un número aproximado es peor que tomarla con una cantidad exacta de
turnos. Si en algún momento la ventana se desborda, esto es lo que hay que
agregar, como tope de seguridad arriba del recorte por turnos.

Sigue disponible como agregado, no como reemplazo: resolvería el peor caso que
el recorte por turnos no acota.

### 5. Resumir lo viejo con el modelo

Pedirle al modelo un resumen de los turnos que salen y mandar el resumen.

Se descarta, y es la que más claro se descarta: un resumen generado por el
modelo es texto que el modelo escribió, no un dato del catálogo. Meterlo en el
contexto como si fuera historial es crear la fuente de invención que todo el
resto del trabajo evita. Si el resumen dice "le interesaba el de 1421.99", ese
precio vuelve a estar a mano sin haberse consultado. Además cuesta una llamada
más al modelo por turno, en CPU.

## La decisión que se tomó

`MAX_TURNS = 2`, en un módulo `backend/history.py`. Se implementó así y es lo
que se midió. El módulo ya no está en el código: ver "Qué pasó".

### Por qué 2

Medido sobre la corrida de siete turnos, en tokens del historial (aproximados
como `len/4`, la misma medida con la que se controla el tamaño del prompt):

| Turno | Entero | N=1 | N=2 | N=3 |
|---|---|---|---|---|
| 1 | 930 | 930 | 930 | 930 |
| 2 | 982 | 982 | 982 | 982 |
| 3 | 1682 | 1682 | 1682 | 1682 |
| 4 | 1841 | 1460 | 1841 | 1841 |
| 5 | 2033 | 1636 | 1652 | 2033 |
| 6 | 2708 | 2232 | 2311 | 2327 |
| 7 | 2767 | 1950 | 2291 | 2370 |

Con N=2 el historial del turno 7 baja de 2767 a 2291 tokens, un 17% menos. El
pedido completo, con los 2800 fijos, baja de unos 5567 a unos 5091: del 68% al
62% de la ventana. N=3 ahorra apenas (2370) y N=1 ahorra bastante más (1950).

Lo que decide entre 1 y 2 no es el ahorro sino qué queda a mano. Con N=1 solo
viaja completo el turno en curso, así que un turno intermedio que no consulte
nada —un "gracias", una repregunta— empuja afuera el resultado al que el usuario
se va a referir después. Con N=2 hay margen para ese turno intermedio. N=2 es el
más chico que deja la conversación funcionando.

### Qué queda de un turno viejo

```
usuario     ¿hay stock del primero?            (queda igual)
asistente   [pide check_availability(...)]      (queda igual, con los argumentos)
tool        Volvé a consultar este dato si...   (el dato se descartó)
asistente   Hay 45 unidades disponibles.        (queda igual)
```

El dato se fue; la constancia de que se consultó el catálogo, no. La frase de
reemplazo no llevaba ningún número, así que no había nada que el modelo pudiera
leer como dato.

### Qué se guardaba y qué viajaba

La sesión guardaba la conversación **entera** (`sessions.SessionStore`). El
recorte era de lo que viajaba al modelo, y lo aplicaba
`assistant.build_messages()`. Así la conversación completa quedaba disponible
para la traza y para poder medir cuánto se recortaba, que es de donde salió la
tabla de arriba.

## Qué pasó

Esto es el desenlace, y es la parte que importa: **el recorte se implementó, se
midió, no mejoró el tiempo, degradó el tool calling y se revirtió.**

Tiempos de los siete turnos, en segundos, en la misma máquina:

| Turno | Antes | Solo 1 y 2, sin recortar | Con los tres cambios |
|---|---|---|---|
| 1 | 3.0 | 2.5 | 2.6 |
| 2 | 7.1 | 6.7 | 7.3 |
| 3 | 55.4 | 68.3 | 65.9 |
| 4 | 17.6 | 17.5 | 18.6 |
| 5 | 10.8 | 13.1 | 12.7 |
| 6 | 24.5 | 73.5 | 91.3 |
| 7 | 21.4 | 53.3 | 48.1 |
| **Total** | **139.8** | **234.9** | **246.5** |

Dos advertencias sobre esta tabla, las dos importantes:

1. **Los totales no son comparables entre columnas**, porque el modelo no toma
   el mismo camino en cada corrida. En la columna "Antes" los turnos 6 y 7
   casi no hicieron nada: el 6 se rindió ante el error del filtro sin volver a
   buscar y el 7 inventó dos product_id que la procedencia rechazó. Hicieron
   menos trabajo, así que tardaron menos. Las columnas donde el turno 6 busca y
   trae cinco productos son las que tardan.
2. **El tiempo en esta máquina varía muchísimo con el mismo código.** La corrida
   guardada en `corrida.log` —mismo código que la columna "Antes", misma
   máquina— suma 1311s, con el turno 7 en 431s. La columna "Antes" de esta tabla
   suma 139.8s. Nueve veces de diferencia sin cambiar una línea. Cualquier
   conclusión de tiempo sacada de una sola corrida no sirve, y por eso lo que se
   usa para justificar N es el tamaño del contexto, que es reproducible.

Lo que sí se ve en los tiempos es que **el historial no es lo que domina**: el
turno 3, con 1682 tokens de historial, tarda 66s; el turno 7, con 2767, tarda
48s. Lo que manda es la cantidad de pasos de herramienta y de tokens generados,
no el tamaño del historial. Recortar 476 tokens de un pedido de 5567 no mueve la
aguja.

### Y le costó el tool calling

| Corrida | Turno 6 | Turno 7 |
|---|---|---|
| Sin recortar | llamó `search_products`, 5 productos reales | llamó `compare_products` |
| Recorte borrando los mensajes | ninguna herramienta, **inventó 3 productos** | ninguna herramienta, inventó la batería |
| Recorte vaciando los resultados | llamó `search_products`, 5 productos reales | ninguna herramienta: anunció la comparación y no la hizo |

Vaciar en vez de borrar recuperó el turno 6, pero el 7 siguió sin llamar la
herramienta, y sin recortar la llamaba. Una corrida por configuración y un modelo
que varía mucho, así que no es prueba concluyente; pero el riesgo apunta todo para
el mismo lado y lo que está en juego es la regla número uno.

### La decisión final: revertir

Se revirtió. El razonamiento:

- La razón de tiempo **no se sostiene**: 476 tokens de 5567, y el historial no es
  lo que domina.
- La razón del RF-07 sí se sostiene en el papel, pero el precio es que el modelo
  deja de consultar el catálogo. Un asistente que no llama a la herramienta no
  cumple el RF-07 mejor: lo cumple peor, porque contesta sin consultar. El remedio
  empujaba al modelo justo hacia la falla que quería evitar.
- No lo pide la letra del obligatorio.

Queda en el código la conversación entera, como estaba. `backend/history.py`,
`tests/test_history.py` y los tests de integración del recorte se borraron; el
comentario de `assistant.build_messages()` apunta a este documento para que nadie
lo vuelva a intentar sin leer la medición primero.

### Si alguien lo retoma

- **`MAX_TURNS = 3`** es el punto intermedio que no se midió: ahorra menos (2370
  contra 2291 tokens en el turno 7) y deja más resultados a mano, así que quizás
  no rompa el turno 7. Es el próximo experimento, no una mejora conocida.
- **La alternativa 4, recortar por tokens**, sigue siendo lo que hay que agregar
  si alguna vez la ventana se desborda de verdad. Hoy no se desborda: el peor
  pedido medido usa el 68% de 8192.
- **Medir con varias corridas por configuración.** Una sola no alcanza con este
  modelo: dos corridas del mismo código dieron 139.8s y 1311s.

## Trade-offs que habría tenido

Se dejan anotados porque son la contracara de la decisión y valen para el próximo
intento:

- **El modelo pierde el detalle de lo que consultó hace tres turnos.** Si el
  usuario vuelve sobre un producto de un turno viejo, tiene que consultarlo de
  nuevo. Eso cuesta una llamada a herramienta, y es el comportamiento que el
  RF-07 pide.
- **N turnos no es una cantidad fija de tokens.** Una conversación de dos turnos
  con dos búsquedas de cinco productos pesa más que diez turnos de charla.
- **Lo que se descarta no vuelve.** No hay manera de que el modelo recupere un
  resultado viejo salvo volviendo a consultar.
- **Le saca al modelo el ejemplo que estaba imitando.** Es el trade-off que no
  habíamos previsto y el que decidió el resultado. Con un modelo de 3B, el
  historial no es solo memoria: es la demostración de cómo se contesta en esta
  conversación.

## Cómo se midió

`scripts/run_conversation.py` corre los siete turnos contra Ollama y el catálogo
real e imprime, en cada turno, lo que contestó el modelo, las herramientas que se
ejecutaron con sus argumentos, cuánto tardó y cuánto ocupa el historial. Mientras
el recorte estuvo en el código imprimía además lo que ocuparía con N=1, 2 y 3, que
es de donde salió la tabla de tokens. Las tres corridas comparadas acá son esa
misma corrida con el recorte apagado, borrando y vaciando.

Los tokens son la aproximación `len/4` sobre el JSON de los mensajes, la misma
medida con la que se controla el tamaño del prompt en `tests/test_prompts.py`.
