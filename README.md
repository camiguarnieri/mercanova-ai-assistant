# MercaNova

Aplicación de e-commerce con un asistente de compras conversacional. El usuario
describe lo que necesita en lenguaje natural y el asistente le recomienda
productos del catálogo real, responde preguntas y lo acompaña hasta completar
una compra ficticia.

El asistente **no inventa datos**: cada precio, stock o especificación que
afirma lo consulta contra la base con *tool calling*. El modelo corre local, con
Ollama.

Obligatorio 2 de Sistemas de Soporte de Decisión, Universidad ORT Uruguay.

---

## Clonar el repositorio

```
git clone https://github.com/camiguarnieri/mercanova-ai-assistant.git
cd mercanova-ai-assistant
```

Esa carpeta es **la raíz del repositorio**, que es desde donde se corren todos
los comandos de este documento. Para confirmar que estás ahí, listá el
contenido: tiene que mostrar `docker-compose.yml`, `requirements.txt` y las
carpetas `backend/` y `frontend/`.

---

## Prerrequisitos

Instalá y dejá andando estas dos cosas **antes** de correr cualquier comando.

### 1. Ollama, con el modelo bajado

Ollama tiene que estar instalado y **corriendo en tu máquina**, no en un
contenedor. Descarga: <https://ollama.com/download>

```
ollama pull qwen2.5:3b
ollama list
```

`ollama list` tiene que mostrar `qwen2.5:3b`. Si no aparece, el chat no va a
funcionar.

**Ollama no va adentro del contenedor, a propósito.** Dos razones:

- **Peso.** La imagen `ollama/ollama` ronda los 3 GB y el modelo son ~1.9 GB
  más. Serían ~5 GB de descarga para algo que ya está instalado en la máquina.
- **Rendimiento.** El modelo corre en CPU y es el cuello de botella del
  proyecto: un turno del chat tarda decenas de segundos. Meterlo en un
  contenedor no lo acelera, y en una máquina con GPU lo haría andar **peor**,
  porque la aceleración no se hereda al contenedor sin configuración extra (y en
  macOS no se puede: Docker no accede a Metal).

El backend corre en el contenedor y llega a tu Ollama por
`host.docker.internal`. El razonamiento completo está en
[docs/decision-dockerizacion.md](docs/decision-dockerizacion.md).

### 2. Docker Desktop, instalado y abierto

Descarga: <https://www.docker.com/products/docker-desktop/>

No alcanza con instalarlo: **tiene que estar abierto y con el motor andando**
antes de correr `docker compose`. Verificá con:

```
docker --version
docker compose version
```

Si querés el camino manual en vez de Docker, Docker Desktop no hace falta: mirá
[Levantarlo sin Docker](#levantarlo-sin-docker-camino-manual).

---

## Levantarlo con Docker

Desde **la raíz del repositorio** (la carpeta que tiene el archivo
`docker-compose.yml`):

```
docker compose up --build
```

No hace falta copiar el `.env` ni configurar nada: el código tiene un valor por
defecto para cada variable y el compose publica los puertos que esos valores
esperan.

**La primera vez tarda varios minutos.** Baja tres imágenes base
(`python:3.13-slim`, `node:22-alpine`, `nginx:1.27-alpine`), instala las
dependencias de Python, corre `npm ci`, compila el frontend y carga las 6662
filas del Excel en la base. Los arranques siguientes son de segundos.

### Qué tenés que ver en los logs

**1. La carga del catálogo** (solo en el primer arranque):

```
La base '/app/data/mercanova.db' está vacía. Cargando el catálogo desde '/app/dataset/MercaNova_dataset.xlsx'...
Catálogo cargado: 6662 filas en 8 tablas.
```

**2. El reporte de configuración**, donde lo importante es el `OLLAMA_HOST`:

```
INFO:     configuración efectiva:
  OLLAMA_MODEL       = qwen2.5:3b (del entorno del proceso)
  OLLAMA_HOST        = http://host.docker.internal:11434 (del entorno del proceso)
  OLLAMA_TIMEOUT     = 300 s por llamada (del entorno del proceso)
  OLLAMA_NUM_CTX     = 8192 tokens (del entorno del proceso)
  OLLAMA_NUM_PREDICT = sin tope propio: lo decide Ollama (default del código)
  OLLAMA_KEEP_ALIVE  = 30m (del entorno del proceso)
  DATABASE_PATH      = /app/data/mercanova.db (del entorno del proceso)
  FRONTEND_ORIGINS   = http://localhost:5173, http://127.0.0.1:5173 (del entorno del proceso)
  .env: no hay archivo en /app/.env, así que se usan el entorno y los defaults
```

Tiene que decir **`http://host.docker.internal:11434`**. Si dice `localhost`, el
contenedor va a buscar Ollama dentro de sí mismo y el chat no va a andar.

Dos cosas de ese bloque que parecen errores y no lo son:

- **"no hay archivo en /app/.env" es lo esperado.** El `.env` no se mete en la
  imagen: las variables las inyecta el compose como variables del proceso. Por
  eso casi todas dicen `(del entorno del proceso)` y no `(del .env)`.
- Si no tenés un `.env`, varias van a decir `(default del código)`. También está
  bien: los defaults son los mismos valores.

**3. El servidor escuchando:**

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Si entre el punto 2 y el 3 aparece `El asistente va a arrancar en frío: ...`, es
que no pudo hablar con Ollama. La API arranca igual y el catálogo funciona, pero
el chat va a dar error: mirá
[el chat da error de conexión al modelo](#el-chat-da-error-de-conexión-al-modelo).

### Verificar que anda

| Qué | Cómo | Qué esperar |
|---|---|---|
| La API | Abrí <http://localhost:8000/brands> en el navegador | El JSON con la lista de marcas |
| La documentación de la API | <http://localhost:8000/docs> | La página de FastAPI |
| La aplicación | <http://localhost:5173> | El catálogo, paginado (son 360 productos en total) |
| El chat | Escribí "necesito auriculares para viajar, hasta 200 dólares" | Una respuesta con productos. **Tarda decenas de segundos**: el modelo corre en CPU |
| El estado de los servicios | `docker compose ps` | El backend en `healthy` (puede tardar hasta 90 s) |

### Apagarlo

```
docker compose down
```

La base sobrevive: vive en un volumen de Docker llamado `mercanova-data`. El
catálogo cargado y las órdenes confirmadas van a estar ahí cuando lo vuelvas a
levantar (y el log va a decir `Catálogo ya cargado ... 360 productos` en vez de
volver a cargarlo).

Los carritos en curso y las conversaciones **no** sobreviven: viven en la
memoria del proceso por decisión de diseño, no por el contenedor.

Para borrar la base y empezar de cero:

```
docker compose down -v
```

---

## Levantarlo sin Docker (camino manual)

Es el camino de desarrollo. Necesitás:

- **Python 3.13** (`python --version`)
- **Node 20.19+ o 22.12+** (`node --version`). Es lo que pide Vite 7
  (`^20.19.0 || >=22.12.0`): Node 18 y Node 21 no sirven.

Hacen falta **dos terminales**: una para el backend y otra para el frontend.

El proyecto se desarrolló y se probó en **Windows**, con PowerShell: los
comandos de esta sección son los que se ejecutaron ahí. Los equivalentes para
macOS y Linux son los estándar, pero no se corrieron en este entorno.

### Terminal 1: el backend

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/load_dataset.py
python -m uvicorn backend.api:app --reload
```

En macOS o Linux, las dos líneas que cambian:

```bash
source .venv/bin/activate
cp .env.example .env
```

`python scripts/load_dataset.py` tiene que imprimir las filas por tabla y
terminar con `Total: 6662 filas en 8 tablas.` Se puede correr de nuevo cuantas
veces quieras: vacía las tablas y las vuelve a cargar.

`python -m uvicorn backend.api:app --reload` se corre **desde la raíz del
repositorio**, no desde dentro de `backend/`. Queda escuchando en
<http://localhost:8000>.

### Terminal 2: el frontend

```powershell
cd frontend
npm install
npm run dev
```

Queda en <http://localhost:5173>.

### Las dos bases de datos son distintas

Esto importa y sorprende:

| Camino | Dónde vive la base |
|---|---|
| Docker | El volumen `mercanova-data` (adentro de Docker) |
| Manual | El archivo `data/mercanova.db` (en la carpeta del repositorio) |

**Los datos no se comparten entre los dos caminos.** Una compra hecha con Docker
no aparece en el historial de órdenes del camino manual, ni al revés. Son dos
instalaciones independientes que corren el mismo código.

Es a propósito: SQLite sobre un *bind mount* de Docker Desktop da errores de
bloqueo intermitentes en Windows y macOS, así que la base del contenedor se
dejó dentro de Docker. Está explicado en
[docs/decision-dockerizacion.md](docs/decision-dockerizacion.md).

---

## Variables de entorno

Toda la configuración está documentada, variable por variable y con el por qué
de cada valor por defecto, en **[`.env.example`](.env.example)**.

```powershell
copy .env.example .env
```

Después editá el `.env`. **No se versiona**, así que un repositorio recién
clonado no lo trae.

No es obligatorio: el código tiene un valor por defecto seguro para cada
variable, y con Docker la aplicación levanta sin `.env`.

Las variables del proyecto son `OLLAMA_MODEL`, `OLLAMA_HOST`, `OLLAMA_TIMEOUT`,
`OLLAMA_NUM_CTX`, `OLLAMA_NUM_PREDICT`, `OLLAMA_KEEP_ALIVE`, `DATABASE_PATH` y
`FRONTEND_ORIGINS`.

### El orden de precedencia

**Una variable puesta en la terminal le gana a la del `.env`.** El `.env` es el
valor del proyecto; la terminal es el de esta corrida. Así que esto funciona
para una prueba puntual, sin tocar el archivo:

```powershell
$env:OLLAMA_MODEL = "llama3.1"
python -m uvicorn backend.api:app --reload
```

El reporte de configuración del arranque dice de dónde salió cada valor: `del
.env`, `del entorno del proceso` o `default del código`. Si dudás de con qué
está corriendo, mirá ese bloque en vez de adivinar.

Con Docker hay una excepción: el compose **reemplaza** `OLLAMA_HOST` por
`http://host.docker.internal:11434`, porque adentro de un contenedor
`localhost` es el contenedor y no tu máquina. El valor del `.env` se ignora
para esa variable, y es lo correcto.

---

## Correr los tests

Los tests **no llaman al modelo ni a la red**: corren sin Ollama prendido.

```powershell
# Backend (desde la raíz, con el entorno virtual activado): 1093 tests
pytest

# Frontend: 24 tests
cd frontend
npm test
```

Con Docker, la suite del backend se puede correr adentro del contenedor:

```
docker compose exec backend python -m pytest -q
```

---

## Problemas frecuentes

### `pytest` no se reconoce como comando

Falta activar el entorno virtual. Se nota en que el prompt de la terminal **no
tiene `(.venv)` adelante**.

```powershell
.venv\Scripts\activate
```

En macOS o Linux: `source .venv/bin/activate`.

El prompt tiene que quedar así:

```
(.venv) PS C:\...\mercanova>
```

Lo mismo vale para `uvicorn` y `python scripts/load_dataset.py`: todos los
comandos del backend necesitan el entorno activado.

> Si al activar aparece `No se puede cargar el archivo ... Activate.ps1 porque
> la ejecución de scripts está deshabilitada en este sistema`, es la política de
> ejecución de PowerShell. Se arregla una vez, para tu usuario:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### `ModuleNotFoundError: No module named 'backend'`

Se corrió `uvicorn` desde adentro de la carpeta `backend/`. Hay que correrlo
**desde la raíz del repositorio**, porque `backend` es el paquete que se importa:

```powershell
cd ..            # si estás dentro de backend/
python -m uvicorn backend.api:app --reload
```

Para confirmar dónde estás: `ls` tiene que mostrar `requirements.txt`,
`docker-compose.yml` y las carpetas `backend/` y `frontend/`.

### `no configuration file provided: not found` al correr `docker compose`

Se corrió desde una carpeta que no es la raíz del repositorio. `docker compose`
busca el `docker-compose.yml` en la carpeta actual.

```powershell
cd C:\ruta\donde\clonaste\mercanova
docker compose up --build
```

Igual que arriba: `ls` tiene que mostrar `docker-compose.yml`.

### El instalador de Docker Desktop falla pidiendo "Virtual Machine Platform"

Falta habilitar WSL 2, que es lo que Docker Desktop usa de motor en Windows.
Abrí una **PowerShell como administrador** (clic derecho en el menú inicio →
*Terminal (Administrador)*) y corré:

```powershell
wsl --install
```

Después **reiniciá la máquina** y volvé a correr el instalador de Docker
Desktop. El reinicio no es opcional: la característica de Windows no queda
activa hasta entonces.

### El chat da error de conexión al modelo

El catálogo, el carrito y el checkout funcionan, pero el chat falla. El backend
no está llegando a Ollama. Tres causas, en orden de probabilidad:

**1. Ollama no está corriendo.** Verificá en tu máquina (no en el contenedor):

```
ollama list
```

Si falla, abrí Ollama. Si lista pero no aparece `qwen2.5:3b`, bajalo con
`ollama pull qwen2.5:3b`.

**2. En Linux, Ollama escucha solo en loopback.** Por defecto se ata a
`127.0.0.1:11434`, que desde la red de Docker no se alcanza. Hay que arrancarlo
atado a todas las interfaces:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

Ojo con el nombre: esa `OLLAMA_HOST` es la **del servidor de Ollama** y
significa *en qué interfaz escucha*. La `OLLAMA_HOST` del `.env` de este
proyecto significa *dónde buscar a Ollama*. Se llaman igual y son cosas
distintas.

En Docker Desktop (Windows y macOS) esto no hace falta. El proyecto se probó en
Windows, así que este comando es el estándar de Ollama para Linux pero no se
ejecutó en este entorno.

**3. El firewall de Windows bloqueó la conexión.** La primera vez que el
contenedor llama a Ollama, Windows puede mostrar un cartel pidiendo
autorización. Si se rechazó, hay que permitir la conexión en la configuración
del firewall.

Para aislar el problema, preguntale al contenedor si llega a Ollama:

```
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5).status)"
```

Tiene que imprimir `200`. Si falla, el problema es la conexión del contenedor a
tu máquina (causas 2 o 3). Si imprime `200` y el chat sigue fallando, el
problema es otro: mirá los logs con `docker compose logs backend`.

### El botón de micrófono no funciona o aparece deshabilitado

La entrada por voz usa la Web Speech API del navegador, que tiene dos
restricciones:

**1. Solo funciona en Chrome y Edge.** Firefox no la implementa y Safari solo
parcialmente. En esos navegadores el botón aparece deshabilitado y la propia
aplicación te dice que hace falta Chrome o Edge. El chat por texto funciona
igual.

**2. Solo funciona sobre `localhost` o HTTPS.** Entrá por
**<http://localhost:5173>**, no por la IP de la máquina
(`http://192.168.x.x:5173`). Con la IP el navegador no considera el origen
seguro y bloquea el micrófono.

Si cumplís las dos y sigue sin andar, lo más probable es que falte el permiso de
micrófono: habilitalo para el sitio desde el ícono de la barra de direcciones.
El detalle está en [docs/decision-voz-a-texto.md](docs/decision-voz-a-texto.md).

---

## Documentación de las decisiones

Cada decisión de diseño que no es obvia está documentada con sus alternativas y
sus trade-offs:

| Documento | De qué trata |
|---|---|
| [decision-dockerizacion.md](docs/decision-dockerizacion.md) | Qué va adentro del contenedor y qué no, por qué un solo proceso, cómo persiste la base |
| [decision-voz-a-texto.md](docs/decision-voz-a-texto.md) | Entrada por voz con la Web Speech API, y por qué no Whisper local |
| [decision-carrito-y-checkout.md](docs/decision-carrito-y-checkout.md) | Qué hace el modelo y qué hace el usuario con el carrito |
| [decision-concurrencia-checkout.md](docs/decision-concurrencia-checkout.md) | Cómo se evitan dos órdenes del mismo carrito |
| [decision-recorte-historial.md](docs/decision-recorte-historial.md) | Un recorte del historial que se implementó, se midió y se revirtió |
| [evidencia-tool-calling.md](docs/evidencia-tool-calling.md) | Evidencia de que el asistente consulta el catálogo en vez de inventar |

Las reglas de desarrollo del proyecto están en [AGENTS.md](AGENTS.md).
