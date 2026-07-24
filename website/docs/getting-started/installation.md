---
sidebar_position: 2
title: "Installation & Setup"
description: "Comprehensive installation guide for Linux, macOS, Windows, Docker, and Cloud environments"
---

# Installation & Setup

This document provides step-by-step instructions for installing and running **Tchuekam Agent** across all supported environments.

---

## 🛠️ Prerequisites

| Dependency | Minimum Version | Recommended | Notes |
|---|---|---|---|
| **Python** | 3.10 | 3.11 / 3.12 | Required for core agent backend |
| **Node.js** | 18.0 | 20.x LTS | Required for Web Dashboard build |
| **npm / pnpm** | 9.0 | 10.x | Node package manager |
| **Git** | 2.30+ | Latest | Version control |
| **Docker** (Optional) | 24.0+ | Latest | For containerized execution |

---

## 📥 Option 1: Native Installation (Recommended)

### Step 1: Clone Repository

```bash
git clone https://github.com/Tchuekam/tchuekam-desktop.git
cd tchuekam-desktop
```

### Step 2: Set Up Python Virtual Environment

```bash
# On Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate

# On Windows (PowerShell):
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Step 3: Install Core Dependencies

```bash
pip install --upgrade pip
pip install -e .
```

### Step 4: Build Web Dashboard Frontend

```bash
cd web
npm install
npm run build
cd ..
```

---

## 🐳 Option 2: Docker & Docker Compose

Deploy with a single command using Docker Compose:

```bash
# 1. Clone repository
git clone https://github.com/Tchuekam/tchuekam-desktop.git
cd tchuekam-desktop

# 2. Configure environment variables
cp .env.example .env

# 3. Start container
docker compose up -d --build
```

Verify running status:

```bash
docker compose ps
docker compose logs -f
```

---

## 🌐 Option 3: Production Cloud Deployment (Railway + Netlify)

Deploying to production on `agent.tchuekam.com`:

### 1. Deploy Railway Backend
```bash
# Authenticate Railway CLI
npx @railway/cli login

# Link and deploy service
npx @railway/cli up --service tchuekam-backend
```

### 2. Deploy Netlify Frontend Proxy
```bash
# Deploy built assets to Netlify
npx netlify-cli deploy --dir hermes_cli/web_dist --prod
```

---

## 🔍 Verification Steps

Run the following validation commands to verify your installation:

```bash
# Test local backend health
curl -s http://localhost:9119/api/status

# Test CLI functionality
python -m hermes_cli.main --version
```

Expected output confirming active installation:
`Tchuekam Agent v0.15.1`

---

## ❓ Common Errors & Resolutions

### 1. `HTTP 401 Unauthorized` on `/api/status`
- **Cause**: Auth gate engages on public binds.
- **Resolution**: Pass `--insecure` when launching backend or ensure `allow_public` is stashed in `web_server.py`.

### 2. `CORS Error: Origin Not Allowed`
- **Cause**: Request origin is not matched by `allow_origin_regex`.
- **Resolution**: Ensure `web_server.py` includes `*.tchuekam.com` and `*.netlify.app` in `CORSMiddleware`.
