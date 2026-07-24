---
sidebar_position: 1
title: "Quickstart"
description: "Your first conversation with Tchuekam Agent — from install to chatting in under 5 minutes"
---

# Quickstart

This guide gets you from zero to a working Tchuekam Agent setup that survives real use. Install, choose an AI provider, verify a working chat, and deploy your web application or cloud backend.

## 🚀 The Fastest Path

Pick the row that matches your goal:

| Goal | Command / Action | Result |
|---|---|---|
| **Local Interactive Chat** | `python run_agent.py` or `hermes` / `hermes --tui` | Interactive CLI or TUI session |
| **Web Dashboard (Local)** | `npm run dev` in `web/` or `python -m hermes_cli.main dashboard` | Local web app on `http://localhost:9119` |
| **Cloud Deployment** | Deploy to Railway + Netlify | Production 24/7 web agent on `agent.tchuekam.com` |
| **Docker Container** | `docker compose up -d` | Containerized agent backend |

---

## 1. Prerequisites

Before installing, ensure your environment meets the following requirements:

- **Python**: `3.10` or higher
- **Node.js**: `18.0` or higher (for Web Dashboard)
- **Package Managers**: `uv` or `pip`, `npm` or `pnpm`
- **Context Length**: AI models require at least **64,000 tokens** of context window.

---

## 2. Local Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/Tchuekam/tchuekam-desktop.git
cd tchuekam-desktop

# Create virtual environment and install Python dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .

# Install Web Dashboard dependencies
cd web
npm install
cd ..
```

---

## 3. Configuration & Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Set your preferred AI model provider API key inside `.env`:

```ini
# Choose your AI Model Provider API Key:
OPENAI_API_KEY=sk-proj-...
# OR
ANTHROPIC_API_KEY=sk-ant-...
# OR
OPENROUTER_API_KEY=sk-or-...

# Product Telemetry (PostHog):
POSTHOG_API_KEY=phx_JurRLsvuQkiD4awJxMybMws47BSpuThTQteQSTwkK6YhdkTy
```

---

## 4. Run the Web Dashboard

Start the Web Dashboard locally:

```bash
# Build web assets and start backend server
npm run build --prefix web
python -m hermes_cli.main dashboard --host 0.0.0.0 --port 9119 --insecure
```

Open your browser at `http://localhost:9119` or `http://localhost:5173` (Vite dev server).

---

## 5. Verify Successful Installation

Run an empirical test against the local status endpoint:

```bash
curl -s http://localhost:9119/api/status
```

Expected JSON response:

```json
{
  "version": "0.15.1",
  "release_date": "2026.5.29",
  "config_version": 26,
  "gateway_running": false
}
```

---

## 6. Cloud Deployment (`agent.tchuekam.com`)

To deploy to Railway & Netlify for 24/7 cloud execution:

1. **Backend (Railway)**: Deploy the container using Railway CLI or GitHub integration (`f3cdfe86-2594-4de2-b212-de85873595e2`).
2. **Frontend & Proxy (Netlify)**: Deploy static files from `hermes_cli/web_dist` with proxy rule in `netlify.toml`:

```toml
[[redirects]]
  from = "/api/*"
  to = "https://tchuekam-backend-production.up.railway.app/api/:splat"
  status = 200
  force = true
```

Your live agent dashboard is immediately accessible at **[https://agent.tchuekam.com](https://agent.tchuekam.com)**.
