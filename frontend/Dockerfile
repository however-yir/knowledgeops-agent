# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS builder
WORKDIR /app

COPY frontend/package.json ./package.json
COPY frontend/package-lock.json ./package-lock.json
COPY frontend/tsconfig.json ./tsconfig.json
COPY frontend/tsconfig.node.json ./tsconfig.node.json
COPY frontend/vite.config.ts ./vite.config.ts
COPY frontend/index.html ./index.html
COPY frontend/src ./src

RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 && \
    npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
