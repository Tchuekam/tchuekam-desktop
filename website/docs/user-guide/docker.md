---
sidebar_position: 7
title: "Docker & Containerization"
description: "Production-grade Docker, Docker Compose, Railway, and Netlify container deployment guide"
---

# 🐳 Docker & Production Containerization

This guide details how to build, configure, run, and scale **Tchuekam Agent** using Docker, Docker Compose, and cloud container environments (Railway + Netlify Edge).

---

## 🏗️ Multi-Stage Dockerfile Architecture

The official `Dockerfile` uses multi-stage builds to optimize image size, security, and build times:

```dockerfile
# Stage 1: Build Web Dashboard Frontend
FROM node:20-slim AS web-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Production Runtime
FROM python:3.11-slim AS runner
WORKDIR /opt/tchuekam

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ffmpeg ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements & application source
COPY . .
RUN python -m venv .venv && \
    .venv/bin/pip install --no-cache-dir -e .

# Copy built frontend static assets from web-builder
COPY --from=web-builder /app/tchuekam_cli/web_dist ./tchuekam_cli/web_dist

# Persistent volume mount point
VOLUME ["/opt/data"]
ENV TCHUEKAM_HOME=/opt/data
EXPOSE 9119

CMD ["/opt/tchuekam/.venv/bin/python", "-m", "tchuekam_cli.main", "dashboard", "--host", "0.0.0.0", "--port", "9119", "--insecure"]
```

---

## 🛠️ Docker Compose Configuration

Create `docker-compose.yml` in your project root:

```yaml
version: "3.8"

services:
  tchuekam-agent:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: tchuekam-agent
    restart: unless-stopped
    ports:
      - "9119:9119"
    environment:
      - TCHUEKAM_HOME=/opt/data
      - PORT=9119
      - POSTHOG_API_KEY=phx_JurRLsvuQkiD4awJxMybMws47BSpuThTQteQSTwkK6YhdkTy
    volumes:
      - tchuekam_data:/opt/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9119/api/status"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

volumes:
  tchuekam_data:
    driver: local
```

---

## ☁️ Deploying to Cloud (Railway + Netlify)

### 1. Railway Container Deployment
Create `.railwayignore` to exclude build caches and virtual environments:

```ini
.venv
venv
node_modules
ui-tui/node_modules
web/node_modules
tchuekam_cli/web_dist
website
docs
```

Deploy via Railway CLI:

```bash
npx @railway/cli up --service tchuekam-backend
```

### 2. Railway Environment Variables

Set required environment variables:

```bash
npx @railway/cli variables set POSTHOG_API_KEY=phx_JurRLsvuQkiD4awJxMybMws47BSpuThTQteQSTwkK6YhdkTy
npx @railway/cli variables set OPENAI_API_KEY=sk-proj-...
```

---

## 🛡️ Persistent Volumes & Backup Strategy

All application state is stored inside `/opt/data`:

| Host Path / Volume | Container Path | Description |
|---|---|---|
| `tchuekam_data` | `/opt/data` | Configuration, API keys, SQLite session databases |
| `config.yaml` | `/opt/data/config.yaml` | Runtime settings |
| `sessions.db` | `/opt/data/sessions.db` | SQLite conversation database |

### Backup Command
```bash
docker exec tchuekam-agent tar -czf /opt/data/backup-$(date +%Y%m%m).tar.gz /opt/data
```

### Restore Command
```bash
docker cp backup-20260724.tar.gz tchuekam-agent:/opt/data/
docker exec tchuekam-agent tar -xzf /opt/data/backup-20260724.tar.gz -C /opt/data
```
