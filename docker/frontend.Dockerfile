# Imagen del frontend de MercaNova: Vite compila los estáticos, nginx los sirve.
#
# Dos etapas para que Node y los node_modules queden solo en la primera: la
# imagen final tiene nginx y los archivos compilados, nada más.
#
# El contexto de build es la raíz del repositorio, no esta carpeta.

# --- Etapa 1: compilar ---
FROM node:22-alpine AS build

WORKDIR /app

# URL de la API. Vite la resuelve **al compilar**, no al arrancar: el valor
# queda escrito dentro del bundle, así que tiene que estar en esta etapa y no
# como variable del contenedor. El default es el mismo que tiene el código en
# frontend/src/api/http.js, y es el puerto que el compose publica.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

# package.json y el lock primero: mientras no cambien, Docker reusa la capa del
# npm ci y no vuelve a bajar las dependencias.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- Etapa 2: servir ---
FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
