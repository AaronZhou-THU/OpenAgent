---
name: dockerfile-builder
description: Build optimized, secure Dockerfiles and docker-compose setups — multi-stage builds, layer caching, security hardening, health checks, networking, volumes, and production-ready templates for Python, Node.js, Go, Rust, and static sites.
---

# Dockerfile Builder Skill

Build production-ready Docker images and compose stacks. Covers multi-stage builds, layer optimization, security hardening, and templates for common tech stacks.

## Core Principles

```
1. Order layers by change frequency — system deps → app deps → source code
2. Use slim/distroless base images — smaller surface area, fewer CVEs
3. Never run as root — always create and switch to non-root user
4. Multi-stage builds — separate build tools from runtime
5. Pin versions — base image tags, package versions, everything
6. .dockerignore — exclude .git, __pycache__, .env, node_modules, .venv
7. Health checks — every service needs one
8. No secrets in images — use build args, env vars, or secret mounts
```

## .dockerignore (always include)

```
.git
.gitignore
.env
.env.*
*.md
LICENSE
docker-compose*.yml
Dockerfile*
.dockerignore
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache
.venv
venv
node_modules
.next
dist
build
coverage
.DS_Store
*.log
```

## Python — FastAPI / Django / Flask

### Production (multi-stage, minimal)

```dockerfile
# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

# System build deps (compiled packages like psycopg2, numpy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into a prefix we can copy
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim

# Runtime system deps only (no compiler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY src/ src/

# Non-root user
RUN useradd -r -s /bin/false -d /app appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### With pyproject.toml (uv/pip)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
COPY --from=builder /install /usr/local
WORKDIR /app
COPY src/ src/

RUN useradd -r -s /bin/false appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### With uv (fast Python package manager)

```dockerfile
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps (cached unless lock changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# Copy app code
COPY src/ src/

RUN useradd -r -s /bin/false appuser
USER appuser
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Django with static files + gunicorn

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
COPY --from=builder /install /usr/local
WORKDIR /app
COPY . .

# Collect static files at build time
RUN python manage.py collectstatic --noinput

RUN useradd -r -s /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000

CMD ["gunicorn", "myproject.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "120", \
     "--access-logfile", "-"]
```

## Node.js — Express / Next.js / Fastify

### Production (multi-stage)

```dockerfile
# ---- Build stage ----
FROM node:20-slim AS builder
WORKDIR /build

# Install deps (cached unless lock changes)
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# Build
COPY . .
RUN npm run build

# Prune dev dependencies
RUN npm prune --production

# ---- Runtime stage ----
FROM node:20-slim

# Security: non-root user (node image has 'node' user built in)
USER node
WORKDIR /home/node/app

# Copy only production deps + built output
COPY --from=builder --chown=node:node /build/node_modules ./node_modules
COPY --from=builder --chown=node:node /build/dist ./dist
COPY --from=builder --chown=node:node /build/package.json .

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))"

CMD ["node", "dist/server.js"]
```

### Next.js (standalone output)

```dockerfile
FROM node:20-slim AS builder
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
USER node
WORKDIR /home/node/app

# Next.js standalone output (minimal)
COPY --from=builder --chown=node:node /build/.next/standalone ./
COPY --from=builder --chown=node:node /build/.next/static ./.next/static
COPY --from=builder --chown=node:node /build/public ./public

EXPOSE 3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
```

### Bun

```dockerfile
FROM oven/bun:1 AS builder
WORKDIR /build
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile
COPY . .
RUN bun run build

FROM oven/bun:1-slim
USER bun
WORKDIR /home/bun/app
COPY --from=builder --chown=bun:bun /build/dist ./dist
COPY --from=builder --chown=bun:bun /build/node_modules ./node_modules
COPY --from=builder --chown=bun:bun /build/package.json .
EXPOSE 3000
CMD ["bun", "run", "dist/server.js"]
```

## Go

### Production (scratch — smallest possible image)

```dockerfile
# ---- Build stage ----
FROM golang:1.22-alpine AS builder

WORKDIR /build

# Cache deps
COPY go.mod go.sum ./
RUN go mod download

# Build static binary
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-s -w" -o /app ./cmd/server

# ---- Runtime stage (scratch = empty image) ----
FROM scratch

# TLS certificates (needed for HTTPS calls)
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Binary
COPY --from=builder /app /app

EXPOSE 8080

ENTRYPOINT ["/app"]
```

### With distroless (shell + basic debugging)

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /app ./cmd/server

FROM gcr.io/distroless/static-debian12
COPY --from=builder /app /app
EXPOSE 8080
ENTRYPOINT ["/app"]
```

## Rust

### Production (multi-stage with cargo-chef for caching)

```dockerfile
# ---- Planner ----
FROM rust:1.77-slim AS planner
RUN cargo install cargo-chef
WORKDIR /build
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

# ---- Builder ----
FROM rust:1.77-slim AS builder
RUN cargo install cargo-chef
WORKDIR /build

# Cache deps (only re-runs when Cargo.toml/lock changes)
COPY --from=planner /build/recipe.json recipe.json
RUN cargo chef cook --release --recipe-path recipe.json

# Build app
COPY . .
RUN cargo build --release

# ---- Runtime ----
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/target/release/myapp /usr/local/bin/myapp

RUN useradd -r -s /bin/false appuser
USER appuser
EXPOSE 8080
CMD ["myapp"]
```

## Static Site (Nginx)

```dockerfile
# ---- Build ----
FROM node:20-slim AS builder
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Serve ----
FROM nginx:1.25-alpine

# Custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Built assets
COPY --from=builder /build/dist /usr/share/nginx/html

# Non-root (nginx alpine supports this)
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s \
    CMD wget -qO- http://localhost:8080/ || exit 1
```

### nginx.conf for SPA

```nginx
server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
}
```

## Docker Compose

### Full-Stack (app + db + cache + reverse proxy)

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        BUILD_ENV: production
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      DATABASE_URL: postgresql://app:${DB_PASSWORD}@db:5432/myapp
      REDIS_URL: redis://cache:6379/0
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      start_period: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '1.0'

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d myapp"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  cache:
    image: redis:7-alpine
    command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    restart: unless-stopped

  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - app
    restart: unless-stopped

volumes:
  pgdata:
  redis-data:
```

### Development (with hot reload + debugging)

```yaml
services:
  app:
    build:
      context: .
      target: builder              # stop at build stage (has dev tools)
    volumes:
      - .:/app                     # mount source for hot reload
      - /app/node_modules          # prevent overwriting container node_modules
    ports:
      - "8000:8000"
      - "5678:5678"                # debugger port
    environment:
      - DEBUG=true
      - DATABASE_URL=postgresql://dev:dev@db:5432/devdb
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: devdb
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

## Security Hardening

```dockerfile
# 1. Non-root user (always)
RUN useradd -r -s /bin/false -d /app appuser
USER appuser

# 2. Read-only filesystem (combine with compose)
# In docker-compose.yml:
#   read_only: true
#   tmpfs:
#     - /tmp
#     - /var/run

# 3. Drop capabilities
# In docker-compose.yml:
#   cap_drop:
#     - ALL
#   cap_add:
#     - NET_BIND_SERVICE    # only if binding to ports < 1024

# 4. No new privileges
# In docker-compose.yml:
#   security_opt:
#     - no-new-privileges:true

# 5. Secrets (never bake into image)
# WRONG:
ENV API_KEY=sk_live_abc123

# RIGHT — use Docker secrets or env at runtime:
# docker run -e API_KEY=sk_live_abc123 myapp

# RIGHT — Docker BuildKit secrets (not stored in layer):
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm ci

# 6. Scan for vulnerabilities
# docker scout cve myimage:latest
# trivy image myimage:latest
```

## Layer Optimization

```dockerfile
# WRONG — each RUN creates a layer; clean up in same layer
RUN apt-get update
RUN apt-get install -y gcc
RUN apt-get clean

# RIGHT — single layer, cleanup included
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# WRONG — COPY everything then install (cache busted on any file change)
COPY . .
RUN pip install -r requirements.txt

# RIGHT — copy deps file first, install, then copy code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Use BuildKit cache mounts for package managers
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

RUN --mount=type=cache,target=/root/.npm \
    npm ci
```

## Useful Commands

```bash
# Build with BuildKit (faster, secret mounts, cache mounts)
DOCKER_BUILDKIT=1 docker build -t myapp:latest .

# Build for specific platform
docker buildx build --platform linux/amd64,linux/arm64 -t myapp:latest .

# Inspect image layers and sizes
docker history myapp:latest
docker inspect myapp:latest

# Scan for vulnerabilities
docker scout cve myapp:latest
trivy image myapp:latest

# Run with resource limits
docker run --memory=512m --cpus=1.0 myapp:latest

# Debug: run shell in container
docker run --rm -it myapp:latest /bin/sh

# Prune unused images/containers/volumes
docker system prune -af --volumes
```

## Best Practices

1. **Order layers by change frequency** — system deps first, app code last
2. **Use slim/alpine/distroless** — smaller attack surface, faster pulls
3. **Never run as root** — always create and switch to non-root user
4. **Multi-stage builds** — separate build tools from runtime image
5. **Pin versions everywhere** — base image, system packages, app dependencies
6. **.dockerignore** — exclude .git, __pycache__, .env, node_modules, .venv
7. **Health checks** — every service in compose needs one, with start_period
8. **One process per container** — don't run supervisor/multiple daemons
9. **Logs to stdout/stderr** — never write to files inside container
10. **Use BuildKit** — `DOCKER_BUILDKIT=1` for cache mounts, secret mounts, parallelism
11. **depends_on with condition** — use `service_healthy` not just `service_started`
12. **Resource limits** — set memory + CPU limits in compose deploy section
