---
sidebar_position: 15
title: "Product Analytics & Telemetry"
description: "PostHog telemetry integration, event tracking, usage analytics, and privacy opt-out"
---

# 📊 Product Analytics & Telemetry

**Tchuekam Agent** incorporates PostHog product analytics to track application usage, active sessions, and download interactions while respecting user privacy.

---

## 🔒 Privacy & Opt-Out Policy

Telemetry is designed with privacy as a first principle:

- **No Code/Prompt Contents**: Prompt history, code contents, and conversation transcripts are **never** transmitted to telemetry services.
- **Anonymous Identification**: Users are assigned a randomly generated distinct ID (`user_<random_hash>`) stored locally.
- **User Opt-Out**: Users can opt out of telemetry at any time.

### How to Opt Out

#### In the Web Dashboard:
Navigate to **Settings** -> **Privacy** -> Toggle **"Disable Telemetry"**.

#### Programmatically in JS/TS:
```typescript
import { setTelemetryOptOut } from "@/lib/posthog";

setTelemetryOptOut(true);
```

#### Via Environment Variable:
Set `HERMES_TELEMETRY_OPT_OUT=1` in your `.env` file.

---

## 📈 Tracked Events

| Event Name | Trigger | Payload Properties |
|---|---|---|
| `app_launched` | Web Dashboard opened in browser | `url`, `referrer`, `user_agent`, `screen_width` |
| `app_download_clicked` | Download button pressed | `platform` (`windows`, `macos`, `linux`) |
| `model_selected` | Model changed in dropdown | `provider`, `model_name` |
| `session_started` | New chat session initialized | `session_id` |

---

## 🛠️ Telemetry Architecture

- **Key**: `phx_JurRLsvuQkiD4awJxMybMws47BSpuThTQteQSTwkK6YhdkTy`
- **Endpoint**: `https://us.i.posthog.com/capture/`
- **Transport**: `navigator.sendBeacon` with `fetch` fallback.
