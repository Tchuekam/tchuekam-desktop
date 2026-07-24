---
sidebar_position: 2
title: "Environment Variables Reference"
description: "Complete reference for all environment variables supported by Tchuekam Agent"
---

# ⚙️ Environment Variables Reference

This page lists all environment variables recognized by **Tchuekam Agent**, categorized by application component.

---

## 🔑 AI Model Provider Credentials

| Variable Name | Description | Example |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API Key | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | `sk-ant-...` |
| `OPENROUTER_API_KEY` | OpenRouter Unified API Key | `sk-or-...` |
| `GOOGLE_API_KEY` | Google Gemini API Key | `AIzaSy...` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | `sk-ds-...` |
| `XAI_API_KEY` | xAI Grok API Key | `xai-...` |

---

## 🌐 Server & Cloud Deployment

| Variable Name | Description | Default | Example |
|---|---|---|---|
| `PORT` | Container bind port for FastAPI server | `9119` | `9119` |
| `RAILWAY_ENVIRONMENT` | Railway cloud environment identifier | *(unset)* | `production` |
| `HERMES_HOME` | Directory path for persistent configuration & state | `~/.hermes` | `/opt/data` |
| `HERMES_ALLOW_PUBLIC` | Bypasses local loopback gate for public binds | `false` | `true` |

---

## 📊 Analytics & Telemetry

| Variable Name | Description | Default |
|---|---|---|
| `POSTHOG_API_KEY` | PostHog product telemetry API key | `phx_JurRLsvuQkiD4aw...` |
| `HERMES_TELEMETRY_OPT_OUT` | Disables telemetry collection when set to `1` | `0` |
