#!/bin/sh
# Punto de entrada del backend: deja el catálogo cargado y después arranca el
# servidor. El comando a ejecutar llega como argumentos, desde el CMD del
# Dockerfile.
#
# `set -e` para que, si la carga del catálogo falla, el contenedor termine con
# error en vez de levantar un servidor sobre una base vacía.
set -e

python /app/docker/ensure_catalog.py

# `exec` reemplaza este shell por uvicorn, así uvicorn queda como PID 1 y recibe
# el SIGTERM de `docker compose down`. Sin exec, el shell se queda en el medio y
# el servidor no se enteraría de que lo están apagando.
exec "$@"
