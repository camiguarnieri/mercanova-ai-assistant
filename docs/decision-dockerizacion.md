# Dockerización (RNF-01, RNF-02): qué va adentro del contenedor y qué no

## Problema

Hace falta que alguien con el repositorio recién clonado corra **un comando** y
le quede la aplicación funcionando, sin instalar Python ni Node a mano. Hoy
levantar el proyecto son cuatro pasos en dos terminales: crear el entorno
virtual, instalar las dependencias, cargar el dataset, arrancar uvicorn, y en
otra terminal `npm install` y `npm run dev`. Funciona, pero depende de que la
máquina tenga las dos plataformas en la versión correcta.

El problema no es escribir un Dockerfile: es que este proyecto tiene cuatro
restricciones que entran en conflicto con lo que un Docker Compose hace por
omisión.

1. **Ollama corre afuera.** Está instalado en la máquina y se queda ahí. El
   backend hoy lo busca en `localhost:11434`, y adentro de un contenedor
   `localhost` es el contenedor, no la máquina: tal cual, el asistente no
   encontraría el modelo.
2. **El servidor tiene que ser un solo proceso.** El candado que serializa el
   checkout vive en la memoria del proceso. Un `--workers 4`, que es lo que
   cualquiera pondría para "aprovechar la máquina", lo rompe en silencio.
3. **La base tiene que sobrevivir al contenedor.** El sistema de archivos de un
   contenedor se borra cuando el contenedor se va. Sin volumen, cada
   `docker compose down` se llevaría el catálogo cargado y las órdenes.
4. **El frontend tiene que quedar en `localhost` del navegador de la máquina.**
   No por comodidad: la entrada por voz (RF-08) usa la Web Speech API, que el
   navegador solo habilita sobre `localhost` o HTTPS. Si la página quedara
   accesible solo por la IP del contenedor, el micrófono deja de funcionar.

Y una restricción más, que es sobre el proceso y no sobre la técnica: **el
camino manual tiene que seguir funcionando igual**. Docker es una alternativa
para quien no quiere instalar nada, no un reemplazo. Dos caminos que se
desincronizan son peores que uno.

## Alternativas consideradas

### 1. No dockerizar y documentar los pasos a mano

Es lo que hay hoy. Se descarta porque es exactamente lo que piden el RNF-01 y
el RNF-02, y porque el riesgo real es la versión de Python: el proyecto usa
3.13, y una máquina con 3.11 falla en cosas que no son obvias. Igual **no se
elimina**: queda como el camino de desarrollo, y es el que usamos nosotras.

### 2. Un solo contenedor con el backend y el frontend adentro

Una imagen que tenga Python y Node, compile el frontend y arranque los dos
servidores. Un contenedor, un comando, nada de redes entre servicios.

Se descarta porque obliga a correr dos procesos con un supervisor
(`supervisord`, o un script que lance uno en background). Eso trae dos
problemas: la imagen tiene dos plataformas instaladas y pesa casi el doble, y
—más importante— **un contenedor con varios procesos no tiene un PID 1 que
maneje bien las señales**, así que `docker compose down` deja procesos
zombis y el apagado se vuelve impredecible. Separar los servicios es lo que
hace que cada contenedor tenga un solo proceso en el frente, que es justamente
lo que este proyecto necesita por la restricción 2.

### 3. Tres contenedores: backend, frontend y Ollama

Es la opción que parece más completa y la que haría un `docker compose up`
realmente autosuficiente: ni siquiera habría que tener Ollama instalado.

Se descarta **por el mismo motivo que Whisper** en
`docs/decision-voz-a-texto.md`, y vale repetirlo porque es el eje con el que se
decide todo en este proyecto:

- **Peso.** La imagen oficial `ollama/ollama` ronda los 3 GB, y encima hay que
  bajar el modelo: `qwen2.5:3b` son ~1.9 GB más, que se descargan la primera vez
  que se usa. Eso convierte un `docker compose up` de un par de minutos en uno
  de bastante más, con 5 GB de descarga.
- **CPU.** El modelo corre en CPU y es el cuello de botella medido del proyecto:
  en la corrida de siete turnos de `corrida.log` el turno más lento tardó
  431 s. Meterlo en un contenedor no lo hace más rápido, y le agrega la capa de
  virtualización de Docker Desktop en Windows y macOS, donde todo corre dentro
  de una VM con la memoria que le haya tocado.
- **La aceleración por GPU no se hereda.** Quien tenga GPU y Ollama instalado
  nativo la está usando. Pasarla a un contenedor necesita el runtime de NVIDIA,
  configuración aparte, y en macOS no se puede: Docker no accede a Metal. O sea
  que en las máquinas donde Ollama anda bien, meterlo en un contenedor lo haría
  andar **peor**.
- **Y duplica el modelo.** Quien ya tiene Ollama con `qwen2.5:3b` bajado se lo
  bajaría de nuevo adentro del volumen del contenedor.

El cálculo es claro: el contenedor de Ollama cuesta ~5 GB y empeora el
rendimiento, y lo único que compra es no tener que instalar Ollama. Como Ollama
ya está instalado en las máquinas donde esto se va a defender, compra nada.

### 4. Dos contenedores (backend y frontend), Ollama afuera — **la que se implementó**

El backend y el frontend en un contenedor cada uno, Ollama en la máquina
anfitriona como hoy, y el backend llegando a él por `host.docker.internal`.

Es la que cumple las cuatro restricciones sin pelearse con ninguna. Lo que
cuesta está en los trade-offs: Ollama queda como un prerrequisito que hay que
instalar aparte, y `host.docker.internal` tiene una limitación real en Linux.

### Cómo sirve el frontend: tres opciones

- **El servidor de desarrollo de Vite (`npm run dev`) adentro del contenedor.**
  Lo descartamos: es un servidor de desarrollo, mantiene Node y los
  `node_modules` en la imagen final (~400 MB entre la base de Node y las
  dependencias) y hace recompilación en caliente que acá no sirve de nada.
- **`vite preview`.** Mejor que el anterior porque sirve el compilado, pero la
  propia documentación de Vite dice que no es para producción, y sigue
  arrastrando Node a la imagen final.
- **Build en varias etapas y nginx sirviendo los estáticos — la elegida.** Node
  queda solo en la etapa de compilación; la imagen final es `nginx:1.27-alpine`
  (~50 MB) más los archivos compilados (~275 KB). Agrega nginx como tecnología,
  que es el costo, pero la configuración son 20 líneas y no hace nada raro: un
  `root`, un `try_files` y dos encabezados de caché.

Una cuarta opción era **servir el `dist` desde FastAPI** con `StaticFiles` y
tener un solo contenedor. Se descartó porque obliga a tocar `backend/api.py`, y
esta tarea es de infraestructura: la aplicación no se modifica. Además mezcla
dos responsabilidades en un servicio que ya tiene la restricción del proceso
único.

### Dónde vive la base: volumen nombrado o bind mount

- **Bind mount de `./data:/app/data`.** La base quedaría en la carpeta del
  repositorio, compartida entre el camino con Docker y el camino manual, y se
  podría abrir con cualquier visor de SQLite desde la máquina. Tentador, pero
  **SQLite sobre un bind mount de Docker Desktop es exactamente el caso que
  conviene evitar**: en Windows y macOS el sistema de archivos del repositorio
  se comparte con la VM por una capa de red (gRPC-FUSE o virtiofs), y el
  bloqueo de archivos de SQLite ahí no es confiable. Son errores de "database
  is locked" intermitentes, el peor tipo de falla para una defensa.
- **Volumen nombrado — el elegido.** `mercanova-data` montado en `/app/data`.
  Vive dentro de la VM de Docker, donde el bloqueo de archivos funciona como en
  Linux nativo, y es más rápido. El costo es que la base no está a mano en la
  carpeta del repositorio: para verla hay que entrar al contenedor.
- **Sin volumen.** Descartada por el enunciado del problema: se perdería el
  catálogo y las órdenes en cada reinicio.

### Cómo se carga el catálogo la primera vez

La base nace vacía, así que alguien tiene que correr la carga del Excel. Cuatro
formas:

- **Documentarlo como un paso manual** (`docker compose exec backend python
  scripts/load_dataset.py`). Descartada: son dos comandos, no uno, y es
  justamente el paso que alguien se va a olvidar. El síntoma sería un catálogo
  vacío sin ningún error, que es el peor síntoma posible.
- **Meter la base ya cargada en la imagen.** Descartada por dos razones: el
  volumen se monta encima de `/app/data` y tapa lo que traiga la imagen, así que
  no funcionaría sin trucos; y una base con datos adentro de una imagen mezcla
  datos con código.
- **Un servicio aparte de tipo "init container"** que cargue y termine, con
  `depends_on: service_completed_successfully`. Es lo más prolijo en despliegues
  grandes, pero acá agrega un tercer servicio al compose, que es una pieza más
  que explicar para hacer lo mismo.
- **Un entrypoint idempotente — el elegido.** `docker/entrypoint.sh` corre
  `docker/ensure_catalog.py` antes de arrancar uvicorn. El script mira cuántos
  productos hay; si hay cero carga el Excel, y si hay carga nada. En el primer
  `up` carga, en todos los siguientes no hace nada.

  El detalle que importa es **por qué pregunta "¿hay productos?" y no "¿existe
  el archivo?"**: `db.connect()` crea el archivo con solo abrirlo, así que su
  existencia no dice nada sobre si tiene datos. Las filas de `products` sí.

  Y no reimplementa la carga: llama a `load_dataset()` de
  `scripts/load_dataset.py`, el mismo que usa el camino manual. La carga sigue
  viviendo en un solo lugar.

## Decisión

**Dos contenedores, Ollama afuera, un volumen nombrado para la base y un
entrypoint que carga el catálogo si falta.** Se levanta con:

```
docker compose up --build
```

Y queda el frontend en `http://localhost:5173` y la API en
`http://localhost:8000`.

### Los archivos

| Archivo | Qué hace |
|---|---|
| `docker-compose.yml` | Levanta los dos servicios, publica los puertos, declara el volumen y resuelve la configuración |
| `docker/backend.Dockerfile` | Imagen del backend: `python:3.13-slim`, uvicorn con un proceso |
| `docker/frontend.Dockerfile` | Imagen del frontend: compila con Node y sirve con nginx, en dos etapas |
| `docker/nginx.conf` | Configuración de nginx para los estáticos compilados |
| `docker/entrypoint.sh` | Carga el catálogo si falta y después ejecuta el CMD |
| `docker/ensure_catalog.py` | La comprobación idempotente y la llamada a la carga |
| `.dockerignore` | Qué no se manda como contexto de build |

No se tocó una línea del backend ni del frontend. El código de la aplicación es
el mismo en los dos caminos.

La imagen del backend copia además **`AGENTS.md` y `.env.example`**, a propósito
aunque no sean código: `tests/test_environment.py` los busca en la raíz del
repositorio —comprueba que el `.env` se resuelva contra ella y que cada variable
del proyecto esté documentada en el ejemplo—, y sin ellos la suite falla adentro
del contenedor y pasa afuera. Que dé el mismo resultado en los dos caminos es el
punto; son dos archivos de texto chicos y el `.env.example` no tiene secretos,
está versionado. El `.dockerignore` excluye los `.md` y los `.env.*`, así que
los dos llevan una excepción explícita ahí.

### Por qué Ollama queda afuera, y cómo lo encuentra el backend

Afuera por lo de la alternativa 3: son ~5 GB entre imagen y modelo, compite por
la misma CPU que ya es el cuello de botella, y en las máquinas con GPU lo haría
andar peor que nativo.

Para encontrarlo, el compose reemplaza `OLLAMA_HOST` en el servicio:

```yaml
environment:
  OLLAMA_HOST: http://host.docker.internal:11434
extra_hosts:
  - "host.docker.internal:host-gateway"
```

`host.docker.internal` es el nombre que resuelve a la máquina anfitriona. En
Docker Desktop (Windows y macOS) ya viene resuelto; en Linux hay que pedirlo con
el `extra_hosts`, que necesita Docker Engine 20.10 o más nuevo. Declararlo en
los tres sistemas no molesta y deja **un solo archivo que funciona en los
tres**, que es lo que se buscaba.

El valor está escrito fijo y no sale de una variable nueva, a propósito:
adentro del contenedor `localhost` nunca es la máquina, así que no hay ningún
caso en el que el `OLLAMA_HOST` del `.env` —que es correcto para el camino
manual— sirva acá. Que el `environment` del compose le gane al `env_file` es
justamente lo que queremos. Si alguna vez Ollama corriera en otra máquina, eso
se cambia con un `docker-compose.override.yml`, que es el mecanismo que Docker
ya tiene para esto, y no agregando una variable al proyecto.

**Las limitaciones de `host.docker.internal`**, que son reales y conviene
conocerlas antes de que aparezcan como un error raro:

- **En Linux, Ollama tiene que escuchar en todas las interfaces.** Por defecto
  Ollama se ata a `127.0.0.1:11434`, que desde el puente de Docker no se
  alcanza: `host-gateway` llega a la máquina por la IP del puente, no por
  loopback. Hay que arrancar Ollama con su propia variable `OLLAMA_HOST` en
  `0.0.0.0:11434`. En Docker Desktop no hace falta porque el proxy de red de la
  VM alcanza el loopback de la máquina.
- **Hay dos variables que se llaman igual y significan cosas distintas.** La
  `OLLAMA_HOST` de este proyecto es *dónde el cliente busca* a Ollama. La
  `OLLAMA_HOST` del servidor de Ollama es *en qué interfaz escucha*. Es una
  confusión fácil y el párrafo anterior habla de la segunda.
- **El firewall de Windows puede preguntar.** La primera vez que el contenedor
  llama a Ollama, Windows puede pedir autorización. Hay que aceptarla.
- **No funciona con Podman tal cual.** Podman usa `host.containers.internal`.
  Si alguien lo corre con Podman, eso se arregla en un override.

### Por qué un solo proceso y no varios

`uvicorn ... --workers 1`, escrito explícitamente en el `CMD` del Dockerfile con
el comentario de por qué, en vez de dejarlo en el default.

El motivo es que **tres cosas de este proyecto viven en la memoria del
proceso**:

- el candado que serializa el checkout por sesión
  (`backend/carts.py`, un `threading.Lock` por sesión en `CartStore`);
- los carritos en curso (`carts.py` lo dice en su docstring: se pierden al
  reiniciar la API);
- las conversaciones del asistente (`backend/sessions.py`, mismo criterio).

Con `--workers 2`, uvicorn arranca **dos procesos de Python con memoria
separada**. Lo que pasa entonces:

- Hay dos `CartStore` distintos. El carrito que armó la sesión aparece o no
  según cuál de los dos procesos atienda el siguiente pedido, que es el que el
  balanceo de uvicorn haya elegido.
- Y lo grave: hay **dos candados distintos** para la misma sesión. El de
  `docs/decision-concurrencia-checkout.md` existe para que dos checkouts del
  mismo carrito no generen dos órdenes. Con dos procesos, cada uno toma su
  propio candado, ninguno espera al otro, y la protección desaparece sin un
  error, sin un log y sin fallar ningún test. El síntoma sería una orden
  duplicada cada tanto.

Un `threading.Lock` sincroniza **hilos**, no procesos. Y eso es suficiente acá
porque uvicorn con un worker atiende todo en un proceso, corriendo los endpoints
sincrónicos en un pool de hilos: los hilos comparten memoria, así que comparten
el candado. Es exactamente el escenario para el que el candado se escribió.

Por eso `--workers 1` no es una decisión de rendimiento que se pueda revisar
"cuando haga falta más capacidad": es lo que hace que el candado proteja algo.
Verificado en el código de uvicorn 0.54 que tiene el proyecto: con
`workers == 1` y sin `--reload`, `main.py` llama a `server.run()` directo, sin
el supervisor de multiproceso.

Si algún día hubiera que escalar a varios procesos, lo que hay que hacer **no**
es subir el número: hay que sacar el estado de la memoria del proceso (carritos
y sesiones a la base, y el candado a una transacción de SQLite o a una fila de
bloqueo). Eso es otro trabajo y está anotado en el documento de concurrencia.

### Cómo se resuelve la persistencia de la base

Un volumen nombrado:

```yaml
volumes:
  - mercanova-data:/app/data
```

y en el servicio, `DATABASE_PATH: /app/data/mercanova.db`, con ruta absoluta
para que no dependa del directorio desde el que se ejecute el proceso.

Lo que sobrevive a `docker compose down` y a un reinicio de la máquina: el
catálogo cargado y las órdenes confirmadas. Lo que no sobrevive, y no es por el
volumen sino porque nunca estuvo en la base: los carritos en curso y las
conversaciones, que viven en memoria por decisión previa del proyecto.

Dos detalles de la implementación que no son obvios:

- **El Excel del dataset no va a `/app/data`.** Va a `/app/dataset`. Si fuera a
  `/app/data`, el volumen se montaría encima y lo taparía. La separación es
  además la correcta: `/app/dataset` es entrada de solo lectura que viene en la
  imagen, `/app/data` es estado que persiste.
- **El volumen nace con el dueño correcto.** El contenedor corre como el usuario
  `mercanova` (uid 1000), no como root. El Dockerfile crea `/app/data` y le pone
  ese dueño **antes** de que exista el volumen, porque cuando Docker crea un
  volumen nombrado vacío copia adentro el contenido y los permisos de ese
  directorio de la imagen. Si no, el volumen sería de root y el proceso no
  podría escribir la base.

Para borrar la base y volver a empezar: `docker compose down -v`. El `-v` es el
que se lleva el volumen; sin él, `down` no lo toca.

### El frontend queda en localhost, y la voz funciona

El servicio publica `5173:80`: nginx escucha en el 80 adentro del contenedor y
Docker lo publica en el **5173 de la máquina**. El navegador abre
`http://localhost:5173`.

Eso es lo que la entrada por voz necesita. La Web Speech API solo funciona en un
contexto seguro, y los navegadores tratan `http://localhost` y
`http://127.0.0.1` como seguros aunque no tengan HTTPS. Así que el micrófono
funciona igual con Docker que sin Docker.

Lo que **no** funciona, y es la contracara: entrar desde otra máquina de la red
por la IP de esta (`http://192.168.x.x:5173`). Ahí el navegador ya no considera
el origen seguro y el botón de micrófono va a mostrar que el servicio está
bloqueado. El chat por texto funciona igual.

El 5173 se eligió además porque es el puerto que `FRONTEND_ORIGINS` ya tiene
habilitado en CORS, y el que el código tiene como default
(`DEFAULT_FRONTEND_ORIGINS` en `backend/api.py`). Con eso, **un repositorio
recién clonado sin `.env` funciona igual**: el `env_file` está declarado con
`required: false`, y todos los defaults del código apuntan a estos mismos
puertos.

### La URL de la API se resuelve al compilar, no al arrancar

Vite reemplaza `import.meta.env.VITE_API_URL` cuando compila, así que el valor
queda escrito dentro del bundle. No es una variable del contenedor: pasarla por
`environment` no tendría efecto. Por eso viaja como `ARG` del build:

```yaml
args:
  VITE_API_URL: ${VITE_API_URL:-http://localhost:8000}
```

El default es el mismo que tiene el código en `frontend/src/api/http.js`. Si
alguien cambia el puerto del backend tiene que **reconstruir** la imagen del
frontend, no solo reiniciarla. Es la trampa más fácil de pisar de toda esta
configuración y por eso está escrita acá y en un comentario del Dockerfile.

### El camino manual no cambió

Sigue siendo el mismo: entorno virtual, `pip install -r requirements.txt`,
`python scripts/load_dataset.py`, `uvicorn backend.api:app --reload`, y
`npm run dev` en `frontend/`. Nada de lo que se agregó lo toca:

- el `.env` es el mismo archivo y las mismas variables;
- `requirements.txt` es el mismo que instala la imagen, a propósito: una sola
  lista, que no se puede desincronizar con la de desarrollo;
- la carga del dataset es el mismo script;
- la base de desarrollo sigue en `data/mercanova.db` y la del contenedor vive en
  el volumen, así que no se pisan.

## Justificación

**El comando único se cumple con lo que ya existe, no con piezas nuevas.** El
compose no inventa configuración: lee el mismo `.env`, llama al mismo script de
carga y corre el mismo código. Lo único que agrega es *dónde* corre.

**Las dos restricciones que se podrían romper en silencio quedan escritas.** El
`--workers 1` está en el `CMD` con el comentario de por qué, y el
`host.docker.internal` también. Son las dos cosas que alguien cambiaría de buena
fe —"pongamos más workers", "localhost ya estaba bien"— y las dos fallan sin dar
un error claro: una duplica órdenes cada tanto, la otra deja al asistente sin
modelo. Dejarlas comentadas en el archivo donde se editan es más efectivo que
dejarlas solo en este documento.

**La decisión de Ollama es la misma que ya se tomó para Whisper, con los mismos
números.** Peso y CPU compartida. Ser consistente importa: es un criterio del
proyecto, no una decisión caso por caso.

**El volumen nombrado evita el modo de falla peor.** SQLite sobre un bind mount
de Docker Desktop da errores de bloqueo intermitentes. Un error intermitente en
una defensa es mucho peor que tener que entrar al contenedor para mirar la base.

**La carga automática elimina el paso que se olvida.** Y su síntoma al
olvidarlo —catálogo vacío, sin error— es el que más caro sale de diagnosticar.

**No se toca la regla número uno.** El asistente sigue consultando el catálogo
con tool calling contra la base. Que la base esté en un volumen y el proceso en
un contenedor no cambia de dónde salen los datos. Esta tarea es de
infraestructura y no toca ni el prompt ni las herramientas.

## Trade-offs

**Ollama es un prerrequisito que hay que instalar aparte.** El `docker compose
up` no es autosuficiente: sin Ollama corriendo en la máquina, el catálogo, el
carrito y el checkout funcionan, pero el chat devuelve el error de conexión al
modelo. Es el precio de no poner 5 GB en la imagen, y está asumido. Quien
levante el proyecto tiene que tener Ollama instalado y `qwen2.5:3b` bajado.

**`host.docker.internal` no es igual en los tres sistemas.** En Docker Desktop
funciona sin tocar nada; en Linux hay que atar Ollama a `0.0.0.0` y tener Docker
Engine 20.10 o más; con Podman el nombre es otro. La configuración es portable
en el sentido de que es un solo archivo, no en el sentido de que no haya nada
que saber.

**La base no está a mano en la carpeta del repositorio.** Vive en el volumen. Es
la contracara de haber evitado el bind mount, y significa que para inspeccionar
la base hay que entrar al contenedor
(`docker compose exec backend python -c "..."`). La base del camino manual
sigue en `data/mercanova.db` y es otra, lo que también quiere decir que **los
dos caminos no comparten datos**: un producto comprado con Docker no aparece en
el historial del camino manual.

**Un cambio en el puerto del backend obliga a reconstruir el frontend.** La URL
de la API se compila dentro del bundle. No es un reinicio, es un
`docker compose build frontend`.

**La imagen del backend instala también las dependencias de desarrollo.**
`pytest` y `httpx` entran porque la imagen usa el mismo `requirements.txt` que
el camino manual. Eso suma unos pocos MB y es deliberado: tener dos listas de
dependencias es un problema más grande que tener pytest en la imagen. Y de paso
permite correr la suite adentro del contenedor, que es la mejor verificación de
que la imagen quedó sana.

**El primer `up` tarda.** Hay que bajar `python:3.13-slim`, `node:22-alpine` y
`nginx:1.27-alpine`, instalar las dependencias de Python —`pandas` es la más
pesada—, correr `npm ci`, compilar el frontend y cargar las 6662 filas del
Excel. Son varios minutos. Los siguientes son segundos, porque Docker reusa las
capas y el catálogo ya está cargado.

**Las imágenes no están fijadas por digest.** Están por versión
(`python:3.13-slim`, `node:22-alpine`, `nginx:1.27-alpine`), que es lo bastante
preciso para un trabajo académico, pero no es reproducible bit a bit: el mismo
`docker compose build` en seis meses puede traer una base con parches
distintos. Para hacerlo reproducible habría que fijar el digest
(`python:3.13-slim@sha256:...`), al costo de tener que actualizarlo a mano.

**No hay configuración para producción.** No hay HTTPS, ni límites de memoria,
ni política de reinicio, ni logs a ningún lado. Es un compose para correr el
proyecto en una máquina, y eso es lo que el obligatorio pide. Poner HTTPS
además complicaría lo único que hoy funciona gracias a `localhost`: la voz.

## Cómo verificar que quedó bien

Esta parte no se pudo probar de punta a punta donde se escribió, porque ahí no
hay Docker instalado. Lo que sí está verificado:

- **La carga automática del catálogo**, corriendo `docker/ensure_catalog.py`
  contra una base vacía en una carpeta temporal: cargó 6662 filas en 8 tablas, y
  la segunda corrida informó "Catálogo ya cargado: 360 productos" sin volver a
  cargar. Es la lógica propia que había que probar.
- **Que `docker-compose.yml` sea YAML válido** y que cada clave quede con el
  valor que se pretendía, en especial el `healthcheck.test` y el
  `${VITE_API_URL:-...}`.
- **Que uvicorn 0.54 con `--workers 1` corra un solo proceso**, leído en
  `uvicorn/main.py`.

Lo que hay que probar en una máquina con Docker Desktop, en orden, está en el
informe de la tarea. En resumen: `docker compose up --build`, verificar en los
logs que el catálogo se cargó y que el reporte de configuración muestra
`OLLAMA_HOST=http://host.docker.internal:11434`, abrir `http://localhost:5173`,
probar el chat (que es lo que prueba que el contenedor llega a Ollama), probar
el micrófono, y después `docker compose down` y `up` de nuevo para confirmar que
la base persistió y que el catálogo no se volvió a cargar.
