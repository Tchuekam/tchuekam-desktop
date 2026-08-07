---
name: docker-containerization
description: "Production containerization, multi-stage Dockerfiles, docker-compose orchestration, and container security."
version: 1.0.0
author: Tchuekam Agent + Antigravity
license: MIT
platforms: [linux, macos, windows]
metadata:
  tchuekam:
    tags: [Docker, DevOps, Containerization, Microservices, Deployment, Security]
    related_skills: [fullstack-nextjs-vite, devops, gcp-dataflow]
---

# Docker Containerization — Production Container Workflows

Build lightweight multi-stage Docker containers, write clean `docker-compose.yml` environment configurations, and perform security lints with Hadolint.

## Core Templates & Patterns

### 1. Optimized Multi-Stage Node/Next.js Dockerfile
```dockerfile
# Stage 1: Dependencies
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Stage 2: Builder
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Stage 3: Runner
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

### 2. Multi-Service Docker Compose Setup
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgres://user:pass@db:5432/mydb
    depends_on:
      - db
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: mydb
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

### 3. Dockerfile Linting
Run Hadolint to check best practices:
```bash
hadolint Dockerfile
```

## Best Practices
- Never run containers as `root` user in production.
- Use explicit base image tags (e.g. `node:20-alpine` instead of `node:latest`).
- Order Dockerfile layers to maximize cache hit rates.
