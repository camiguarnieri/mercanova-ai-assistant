# Imagen del backend de MercaNova: FastAPI servido por uvicorn, en UN proceso.
#
# Ollama no está acá: corre en la máquina anfitriona y el contenedor lo busca
# por host.docker.internal. El por qué está en docs/decision-dockerizacion.md.
#
# El contexto de build es la raíz del repositorio, no esta carpeta.

FROM python:3.13-slim

# PYTHONUNBUFFERED es el que importa: sin él, el log de arranque que escribe
# config_report queda en el buffer y no aparece en `docker compose logs` cuando
# se produce, que es justo cuando hace falta leerlo.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# Las dependencias en su propia capa y antes del código: mientras
# requirements.txt no cambie, Docker reusa esta capa y no reinstala nada.
# Es el mismo requirements.txt que usa el camino manual, a propósito: una sola
# lista que no se puede desincronizar con la de desarrollo.
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

# AGENTS.md y .env.example no son código, pero `tests/test_environment.py` los
# busca al lado del código: comprueba que el .env se resuelva contra la raíz del
# repositorio y que cada variable del proyecto esté documentada en el ejemplo.
# Sin ellos la suite falla adentro del contenedor y pasa afuera, que es la peor
# clase de diferencia entre los dos caminos. Son dos archivos de texto chicos.
# Van antes del código porque cambian menos: así Docker reusa más capas.
COPY AGENTS.md .env.example ./

# El código de la aplicación. `tests/` también entra, para poder correr la
# suite adentro del contenedor y verificar que la imagen quedó sana.
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY docker/entrypoint.sh docker/ensure_catalog.py ./docker/

# El Excel del dataset va a /app/dataset y NO a /app/data, a propósito:
# /app/data es el volumen donde vive la base y se monta encima de lo que traiga
# la imagen. Acá el Excel solo se lee; el original del repositorio no se toca.
COPY data/MercaNova_dataset.xlsx /app/dataset/
ENV DATASET_EXCEL=/app/dataset/MercaNova_dataset.xlsx

# Usuario sin privilegios. /app/data se crea y se le asigna acá para que el
# volumen nazca con el dueño correcto: Docker copia el contenido y los permisos
# de este directorio cuando crea un volumen nombrado vacío.
RUN useradd --create-home --uid 1000 mercanova \
    && mkdir -p /app/data \
    && chown -R mercanova:mercanova /app \
    && chmod +x /app/docker/entrypoint.sh
USER mercanova

EXPOSE 8000

# El entrypoint deja el catálogo cargado y después ejecuta el CMD.
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# UN SOLO PROCESO, escrito a propósito y no por omisión.
#
# El candado que serializa el checkout (backend/carts.py) es un threading.Lock
# que vive en la memoria de este proceso, y los carritos en curso también. Con
# --workers 2 cada proceso tendría su propia memoria: dos candados distintos
# que no se ven entre sí, y un carrito que aparece o no según qué worker
# atienda el pedido. --workers 1 no es una opción de rendimiento, es lo que
# hace que el candado proteja algo. No subir sin leer
# docs/decision-dockerizacion.md y docs/decision-concurrencia-checkout.md.
CMD ["python", "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
