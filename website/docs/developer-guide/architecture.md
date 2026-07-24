---
sidebar_position: 1
title: "System Architecture"
description: "Comprehensive technical architecture of Tchuekam Agent — monorepo, web dashboard, cloud containerization, and process model"
---

# 🏗️ System Architecture

**Tchuekam Agent** is a full-stack, cross-platform AI agent framework. It provides interactive terminal interfaces (CLI and TUI), a rich web dashboard (React 19 SPA), a FastAPI backend API, 24/7 cloud containerization (Railway + Netlify Edge), and PostHog product analytics telemetry.

---

## 📐 Top-Level Component Architecture

```mermaid
flowchart TD
    subgraph ClientLayer["📱 Client Layer"]
        WebSPA["React 19 Web Dashboard (web/)"]
        TUI["Ink / React Terminal UI (ui-tui/)"]
        CLI["Rich / prompt_toolkit CLI (cli.py)"]
    end

    subgraph EdgeLayer["⚡ Edge & Routing Layer (Netlify)"]
        NetlifyEdge["Netlify CDN (agent.tchuekam.com)"]
        ProxyRule["Proxy Rewriter (/api/* -> Railway)"]
    end

    subgraph CloudBackend["☁️ Cloud Backend Layer (Railway Container)"]
        FastAPI["FastAPI Web Server (hermes_cli/web_server.py)"]
        CORS["CORS Middleware (*.tchuekam.com)"]
        AuthGate["Cloud Public Middleware"]
        AgentEngine["AIAgent Engine (run_agent.py)"]
        PTYBridge["PTY WebSocket Bridge (/api/pty)"]
        ToolRegistry["Tool Registry (tools/registry.py)"]
        SessionDB[("SQLite Storage (/opt/data/sessions.db)")]
    end

    subgraph Analytics["📊 Analytics & Telemetry"]
        PostHog["PostHog Product Telemetry (us.i.posthog.com)"]
    end

    WebSPA -->|HTTPS / WSS| NetlifyEdge
    NetlifyEdge --> ProxyRule --> FastAPI
    WebSPA -->|Telemetry Events| PostHog
    FastAPI --> CORS --> AuthGate --> AgentEngine
    FastAPI --> PTYBridge --> TUI
    AgentEngine <--> ToolRegistry
    AgentEngine <--> SessionDB
```

---

## 🔍 Core Subsystem Breakdown

### 1. Web Dashboard SPA (`web/`)
- **Framework**: React 19, TypeScript, Vite, Tailwind CSS / Vanilla CSS design tokens.
- **State Management**: Nanostores & React hooks.
- **API Client**: `web/src/lib/api.ts` handles REST endpoints (`/api/status`, `/api/models`, `/api/sessions`).
- **Telemetry**: `web/src/lib/posthog.ts` provides privacy-conscious PostHog product telemetry (`POSTHOG_API_KEY = phx_JurRLsvu...`).

### 2. Backend Web Server (`hermes_cli/web_server.py`)
- **Engine**: FastAPI async server running on Uvicorn.
- **Proxy Middleware**:
  - `CORSMiddleware`: Configured to permit requests from `*.tchuekam.com`, `*.netlify.app`, `*.up.railway.app`, `localhost`, and `127.0.0.1`.
  - `auth_middleware`: Grants public read access to `/api/status`, `/api/config/defaults`, `/api/model/info`, and `/api/dashboard/themes` when deployed in cloud environments (`is_cloud`).

### 3. Edge Reverse Proxy (`netlify.toml`)
- Netlify routes static web assets for `agent.tchuekam.com` while proxying `/api/*` requests to the Railway cloud container:
  ```toml
  [[redirects]]
    from = "/api/*"
    to = "https://tchuekam-backend-production.up.railway.app/api/:splat"
    status = 200
    force = true
  ```

### 4. Cloud Containerization (Railway)
- Running 24/7 in an isolated Linux container.
- **Data Persistence**: Mounts `/opt/data` for `config.yaml`, `.env`, `SOUL.md`, `sessions/`, and SQLite databases.
- **Start Command**: `python -m hermes_cli.main dashboard --host 0.0.0.0 --port $PORT --insecure`.

---

## 🔄 Data & Execution Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Web as Web Dashboard (agent.tchuekam.com)
    participant Netlify as Netlify Edge Proxy
    participant Railway as Railway FastAPI Backend
    participant Agent as AIAgent Core Loop
    participant Telemetry as PostHog Telemetry

    User->>Web: Open https://agent.tchuekam.com
    Web->>Telemetry: Send app_launched event
    Web->>Netlify: GET /api/status
    Netlify->>Railway: Proxy GET https://tchuekam-backend/api/status
    Railway-->>Netlify: 200 OK {version: "0.15.1", config_version: 26}
    Netlify-->>Web: 200 OK JSON Data
    Web-->>User: Render live dashboard without errors
```
