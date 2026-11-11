# Entrada por voz (RF-08): de dónde sale la transcripción

## Problema

El RF-08 pide que, además de texto, el usuario pueda consultar por voz: la
aplicación tiene que convertir el audio a texto y procesarlo **como una consulta
normal**. No pide síntesis de voz ni un agente conversacional por voz: pide
transcripción.

Esa última parte es la que define el diseño. Si el audio se convierte a texto y
el texto entra al mismo flujo que ya existe, la funcionalidad no toca nada del
asistente: no hay un prompt nuevo, no hay una herramienta nueva, no cambia el
backend. Lo único que hay que decidir es **quién transcribe** y **dónde corre**.

La decisión importa porque el paso siguiente del obligatorio es empaquetar todo
en Docker Compose. Cualquier cosa que agreguemos al backend se la lleva la
imagen, y eso es tiempo de build, peso de imagen y tiempo de arranque para
cualquiera que corra el proyecto, incluido el tribunal en la defensa.

## Alternativas consideradas

### 1. Web Speech API del navegador — **la que se implementó**

El navegador expone `SpeechRecognition` (con prefijo `webkitSpeechRecognition`
en Chrome). Se le pide escuchar, se le configura el idioma, y devuelve el texto
transcripto en un evento. No hay código de servidor, no hay dependencias nuevas,
no hay audio que viaje por nuestra API.

A favor: cero costo en la imagen de Docker, cero dependencias nuevas en el
`package.json` de producción, y el audio nunca pasa por nuestro backend, así que
no hay nada que almacenar ni que manejar.

En contra: es la única alternativa que depende de un servicio que no
controlamos. Está en los trade-offs, que es donde duele.

### 2. Transcripción local con Whisper en el backend

Pedida explícitamente por la cátedra para que quede documentada, aunque no se
implemente. El frontend grabaría el audio con `MediaRecorder`, lo subiría a un
endpoint nuevo (`POST /voice/transcribe`), y el backend lo transcribiría con
Whisper corriendo en la misma máquina. Todo local, sin servicios externos.

Es la alternativa **técnicamente mejor en lo que importa conceptualmente**: el
audio no sale de la máquina, funciona en cualquier navegador que pueda grabar
(incluido Firefox), funciona offline y no depende de HTTPS. Si el criterio fuera
solo la calidad de la solución, gana esta.

Lo que la descarta es el costo, y conviene ponerlo en números. Dos formas de
instalarla, con lo que cada una agrega a la imagen:

| | `openai-whisper` | `faster-whisper` (CTranslate2) |
|---|---|---|
| Dependencia pesada | PyTorch CPU (~900 MB instalado, ~200 MB de descarga) | CTranslate2 (~50 MB instalado) |
| `ffmpeg` en la imagen | obligatorio (~80 MB con sus dependencias) | obligatorio (~80 MB con sus dependencias) |
| Pesos del modelo | `tiny` 75 MB · `base` 142 MB · `small` 466 MB | `base` int8 ~75 MB · `small` int8 ~250 MB |
| **Suma sobre `python:3.13-slim` (~150 MB)** | **~1.3 GB** con `base` | **~430 MB** con `base` int8 |

Los números son los tamaños publicados de las ruedas y de los pesos, no una
medición nuestra: no se instaló. Sirven para el orden de magnitud, que es lo que
decide.

Además del peso, los dos costos que se pagan cada vez:

- **Tiempo de build.** Instalar PyTorch CPU en una imagen limpia son varios
  minutos de descarga y descompresión, y es la capa más grande de la imagen: se
  reconstruye cada vez que cambia `requirements.txt`. Hoy lo más pesado que
  instala el backend es `pandas` (~70 MB, y solo lo usa el script de carga del
  Excel); PyTorch es un orden de magnitud más que eso.
- **Tiempo de arranque y de respuesta.** Los pesos se cargan en memoria la
  primera vez que se transcribe (o al arrancar, si se precarga para que la
  primera consulta no espere). Y la transcripción en sí compite por CPU con
  Ollama, que es lo que ya tenemos corriendo ahí y lo que ya es el cuello de
  botella: el modelo de 3B corre en CPU y un turno con herramientas tarda
  decenas de segundos. Agregarle una transcripción en la misma CPU empeora lo
  que ya es lo más lento del sistema.

Ese último punto es el que la mata, más que el peso. La máquina donde esto corre
ya está saturada por el LLM.

**Queda como el camino a seguir si el requerimiento cambia**: si hubiera que
soportar Firefox, servir sin HTTPS, o si apareciera la exigencia de que el audio
no salga de la máquina, esto es lo que hay que implementar, con `faster-whisper`
y el modelo `base` en int8, que es la combinación que da el salto de peso más
chico.

### 3. Una API de transcripción paga (OpenAI Whisper API, Google Speech-to-Text, Deepgram)

Se descarta rápido, por dos razones independientes. La primera es que el audio
sale igual de la máquina, así que no compra nada sobre la alternativa 1 en ese
eje, que es justamente el único eje donde la 1 pierde. La segunda es que necesita
una clave paga y una cuenta: el proyecto se tiene que poder correr con un `docker
compose up` y nada más. El resto del sistema es local a propósito —el LLM es
Ollama corriendo en la máquina—, y meter un servicio pago para la transcripción
va contra esa línea.

### 4. Un Voice Agent (voz a voz, con el asistente respondiendo hablado)

No lo pide el RF-08. Se descarta por alcance: agrega síntesis de voz, manejo de
turnos y latencia sobre un asistente que ya tarda decenas de segundos por turno
en CPU. Se anota para que quede claro que se consideró y que la decisión de no
hacerlo es deliberada, no un olvido.

## Decisión

**Web Speech API del navegador, solo transcripción, sin envío automático.**

Tres archivos, todos de frontend. El backend no se tocó:

- `frontend/src/useSpeechRecognition.js` — envuelve la API del navegador y la
  expone como un hook con tres cosas: si se puede usar, si está escuchando y qué
  salió mal. Acá vive la traducción de cada código de error de la API al mensaje
  que ve el usuario.
- `frontend/src/components/VoiceInput.jsx` — el botón de micrófono y el aviso de
  estado. Recibe un `onTranscript` y no sabe nada del chat.
- `frontend/src/pages/Chat.jsx` — pone el botón al lado del campo de texto y, con
  el texto transcripto, **escribe en el campo**. Nada más.

Las decisiones de comportamiento:

- **Idioma `es-UY`**, en `DEFAULT_LANG`.
- **`continuous = false` e `interimResults = false`**: una consulta por vez, y el
  texto llega una sola vez y completo. No hay texto provisorio parpadeando en el
  campo.
- **El texto no se manda solo.** Aparece escrito en el campo y el usuario aprieta
  Enviar, igual que si lo hubiera tecleado. Si ya había algo escrito, lo dictado
  se agrega al final en vez de reemplazarlo.
- **Estado de escucha visible**: el botón se pinta con el color de alerta y late,
  y abajo del formulario aparece "Escuchando...". La animación se apaga con
  `prefers-reduced-motion`.
- **El botón queda deshabilitado mientras se está mandando un mensaje**, igual
  que el de Enviar.

### Los cuatro casos límite

Cada código de error de la API se traduce a un mensaje que dice qué hacer. El
código nunca se le muestra al usuario. Están todos juntos en `SPEECH_MESSAGES`:

| Situación | Código de la API | Qué ve el usuario |
|---|---|---|
| Navegador sin la API (Firefox) | — | Botón deshabilitado, con el texto de que hace falta Chrome o Edge y que mientras tanto escriba |
| Permiso de micrófono negado | `not-allowed` | Que habilite el micrófono para el sitio desde el ícono de la barra de direcciones |
| Silencio o nada reconocible | `no-speech`, o terminar sin texto ni error | "No te escuché. Apretá el micrófono y probá de nuevo." |
| Error de red | `network` | Que no se pudo conectar con el servicio y que revise la conexión |
| Sin micrófono conectado | `audio-capture` | Que conecte uno y le dé permiso |
| Servicio bloqueado por el navegador | `service-not-allowed` | Que solo funciona sobre HTTPS o en localhost |
| Cualquier otro código | cualquiera | Mensaje genérico accionable, sin el código |
| Cancelación del propio usuario | `aborted` | Nada: no es un error |

Dos de esas filas no estaban en la lista de casos límite y se agregaron porque
salen del mismo lugar: `audio-capture` y `service-not-allowed` son códigos que la
API devuelve de verdad, y sin tratarlos caían en el mensaje genérico.

El caso de "terminar sin texto y sin error" también se agregó: la API puede
cerrar el micrófono sin haber transcripto nada y sin informar `no-speech`. Para
el usuario es indistinguible del silencio, así que recibe el mismo mensaje. Sin
eso, el botón volvía a su estado normal sin decir nada y parecía que se había
perdido lo que dijo.

## Justificación

**El requerimiento es transcripción, y el navegador ya la trae.** Convertir audio
a texto es exactamente lo que hace la Web Speech API. Todo lo que agregaríamos
con cualquier otra alternativa es infraestructura para llegar al mismo texto.

**El costo en Docker es cero, y el paso siguiente es Docker.** No hay dependencia
nueva en producción, no hay capa nueva en la imagen, no hay pesos de modelo que
descargar en el build. La alternativa 2 agrega entre 430 MB y 1.3 GB a una
imagen que hoy pesa lo que pesan FastAPI y Pydantic.

**La CPU de esta máquina ya está ocupada por Ollama.** Es el argumento más fuerte
y es específico de este proyecto: el LLM corre en CPU y es el cuello de botella
medido. Poner la transcripción en el mismo lugar empeora lo que ya es lo más
lento.

**No toca la regla número uno.** El texto transcripto es una consulta del
usuario, igual que una tecleada, y entra por el mismo camino: mismo endpoint,
mismo prompt, mismas herramientas. El modelo sigue sin poder afirmar un precio o
un stock que no consultó. Que el usuario haya hablado en vez de escribir no le
da al modelo ningún dato nuevo. Por eso esto es puro frontend y por eso no hay
nada que revisar del lado del asistente.

**No mandar solo es una decisión, no una simplificación.** El reconocimiento se
equivoca, sobre todo con marcas y modelos, que es justo el vocabulario de este
catálogo. Si el texto se mandara solo, un "NovaTech" mal transcripto se
convierte en un turno perdido de decenas de segundos. Dejarlo escrito en el
campo le da al usuario la corrección gratis, y mantiene una sola forma de
mandar un mensaje.

**Es explicable en la defensa.** Un hook de 150 líneas que envuelve una API del
navegador y una tabla de siete mensajes de error. Cualquiera del equipo lo puede
defender línea por línea.

## Trade-offs

**El audio se procesa en servidores de Google, no localmente.** Esto es lo más
importante del documento y es la contracara directa de la decisión. En Chrome, la
Web Speech API no transcribe en el dispositivo: manda el audio del micrófono a
los servidores de reconocimiento de Google y recibe el texto. No es nuestro
servidor ni nuestra elección de proveedor, y no tenemos forma de cambiarlo desde
el código: es cómo el navegador implementa la API. Es la única parte del sistema
que sale de la máquina del usuario —el LLM es local, la base es local, el
catálogo es local— y por eso se documenta acá y no en una nota al pie. La
alternativa 2 es la que arregla esto, y el costo de arreglarlo es el de esa
sección.

**Solo funciona en Chrome y Edge.** Firefox no implementa `SpeechRecognition`, y
Safari lo hace parcialmente. En esos navegadores el botón aparece deshabilitado y
explica qué hace falta. La aplicación sigue funcionando entera: el chat por texto
no cambia en nada. La funcionalidad se degrada, no se rompe.

**Solo funciona sobre localhost o HTTPS.** Es la restricción del navegador para
cualquier API que acceda al micrófono. En desarrollo no molesta porque todo corre
en `localhost`. Si alguna vez esto se sirve desde una IP sin certificado, el
micrófono no va a andar y el navegador va a devolver `service-not-allowed`, que
está tratado con el mensaje que lo dice.

**Depende de que haya internet**, aunque el resto de la aplicación no. El
asistente funciona offline: Ollama y SQLite son locales. El micrófono no. Es una
asimetría rara y vale decirla en voz alta: es el único punto del sistema donde
cortar internet rompe algo.

**La calidad de la transcripción no la controlamos.** No podemos ajustar un
modelo, darle vocabulario del catálogo ni mejorar cómo reconoce nombres de marca.
Si transcribe mal "NovaTech", lo arregla el usuario en el campo de texto. Eso es
parte de por qué no se manda solo.

**No hay dictado continuo.** `continuous = false` significa una consulta por
turno: hay que apretar el micrófono de nuevo para dictar otra vez. Para una
consulta de catálogo alcanza, y evita tener el micrófono abierto sin que el
usuario se dé cuenta.

## Qué no se puede probar con un test automático

Vale dejarlo escrito, porque la cobertura de esta funcionalidad se ve más alta de
lo que es. Los tests están en `frontend/tests/VoiceInput.test.jsx` (18 casos) y
`frontend/tests/Chat.test.jsx` (6 casos), y usan el doble de
`frontend/tests/speechMock.js`, que instala un `webkitSpeechRecognition` falso en
`window`: jsdom no trae la API de verdad.

**Lo que los tests sí prueban** es todo lo que es nuestro: con qué se configura
el reconocimiento (`es-UY`, `continuous` y `interimResults` en false), qué
muestra la interfaz en cada estado, que cada código de error se traduzca al
mensaje correcto, que el texto llegue limpio al campo, que no se mande solo, y
que el botón quede deshabilitado y explicado cuando la API no existe. Es el mismo
criterio que usamos con el LLM en el backend: se verifica **lo que se le mandó**,
no lo que contestó.

**Lo que no se puede probar automáticamente**, y por qué:

- **El reconocimiento de voz en sí.** Que un audio con "necesito auriculares para
  viajar" produzca ese texto depende del motor de Google. No hay nada nuestro en
  el medio y no hay forma de ejercitarlo sin audio real, un micrófono y un
  navegador de verdad.
- **El permiso del micrófono.** El diálogo de permiso lo dibuja el navegador,
  fuera de la página. En el test se dispara el `not-allowed` que la API devuelve
  *después* de que el usuario negó; que negar efectivamente produzca ese código
  es comportamiento del navegador.
- **El timeout de silencio.** Cuánto espera la API antes de darse por vencida con
  `no-speech` lo decide la implementación del navegador y no es configurable. El
  test simula el evento, no la espera.
- **El error de red de verdad.** Se simula el código `network`. Cortar la conexión
  al servicio de Google durante un reconocimiento no es algo que se pueda hacer
  desde jsdom.
- **Que el botón efectivamente no aparezca usable en Firefox.** Se prueba la rama
  "la API no está en `window`", que es la condición que lo causa. Que Firefox no
  la tenga es un hecho sobre Firefox, no sobre nuestro código.
- **La animación de "escuchando".** El test verifica que la clase y el texto
  estén. Que se vea bien y se entienda es inspección visual.

En resumen: los tests cubren la lógica y la interfaz completas, y no cubren nada
de lo que pasa del navegador para afuera. **La funcionalidad hay que probarla a
mano en Chrome, sobre `localhost`, hablándole.** Eso no es una deuda: es el
límite de dónde termina nuestro código.

## Infraestructura de tests que trajo esto

El frontend no tenía tests. Esta funcionalidad los necesitaba, así que se agregó
lo mínimo para correrlos, todo en `devDependencies`: `vitest` (ya teníamos Vite,
así que comparte la configuración), `jsdom`, `@testing-library/react` y
`@testing-library/jest-dom`. La configuración está en el bloque `test` de
`frontend/vite.config.js`, y se corre con `npm test` desde `frontend/`.

`frontend/tests/setup.js` tiene un detalle que conviene conocer: define
`Element.prototype.scrollIntoView`, porque jsdom no lo implementa y el chat lo
usa para seguir la conversación. No es un parche a nuestro código; es una pieza
del DOM que jsdom no trae.
