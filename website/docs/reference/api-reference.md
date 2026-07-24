---
sidebar_position: 1
title: "API Reference"
description: "Complete REST API reference and WebSocket specification for Tchuekam Agent Web Server"
---

# 📡 REST & WebSocket API Reference

The **Tchuekam Agent** FastAPI backend exposes REST endpoints for system status, model management, session inspection, configuration defaults, and real-time PTY terminal streaming over WebSockets.

Base URL (Cloud): `https://agent.tchuekam.com/api`  
Direct Railway URL: `https://tchuekam-backend-production.up.railway.app/api`

---

## 🟢 Public Endpoints

### 1. `GET /api/status`
Returns agent system version, release date, and gateway status.

- **Auth Required**: No (Public)
- **Response `200 OK`**:
```json
{
  "version": "0.15.1",
  "release_date": "2026.5.29",
  "hermes_home": "/opt/data",
  "config_path": "/opt/data/config.yaml",
  "env_path": "/opt/data/.env",
  "config_version": 26,
  "latest_config_version": 26,
  "gateway_running": false
}
```

---

### 2. `GET /api/config/defaults`
Returns default configuration values and options.

- **Auth Required**: No (Public)
- **Response `200 OK`**:
```json
{
  "model": "anthropic/claude-sonnet-4.6",
  "terminal.backend": "local",
  "display.skin": "default"
}
```

---

### 3. `GET /api/model/info`
Returns AI model metadata and context window details.

- **Auth Required**: No (Public)
- **Response `200 OK`**:
```json
{
  "default_model": "anthropic/claude-sonnet-4.6",
  "min_context_length": 65536
}
```

---

## 🔒 Authenticated Endpoints

### 4. `GET /api/sessions`
Returns a list of active conversation sessions.

- **Auth Required**: Yes (`X-Hermes-Session-Token` or `--insecure` mode)
- **Response `200 OK`**:
```json
{
  "sessions": [
    {
      "id": "session_12345",
      "created_at": "2026-07-24T00:00:00Z",
      "model": "anthropic/claude-sonnet-4.6",
      "message_count": 12
    }
  ]
}
```

---

### 5. `GET /api/auth/me`
Returns current authenticated user or session profile information.

- **Auth Required**: Yes (`X-Hermes-Session-Token`)
- **Response `200 OK`**:
```json
{
  "authenticated": true,
  "user_id": "user_admin"
}
```

---

## 🔌 WebSocket Endpoints

### 6. `WS /api/pty`
Interactive terminal PTY bridge for the embedded Web Dashboard terminal emulator.

- **Protocol**: WebSocket
- **URL**: `wss://agent.tchuekam.com/api/pty?token=<SESSION_TOKEN>`
- **Frame Format**: Raw PTY terminal bytes in UTF-8 format.
- **Resize Frame**: Send `\x1b[RESIZE:<cols>;<rows>]` to change terminal dimensions.
