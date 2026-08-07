# Langfuse Observability Plugin

This plugin ships bundled with Tchuekam but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
tchuekam tools  # → Langfuse Observability

# Manual
pip install langfuse
tchuekam plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.tchuekam/.env` (or via `tchuekam tools`):

```bash
TCHUEKAM_LANGFUSE_PUBLIC_KEY=pk-lf-...
TCHUEKAM_LANGFUSE_SECRET_KEY=sk-lf-...
TCHUEKAM_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
tchuekam plugins list                 # observability/langfuse should show "enabled"
tchuekam chat -q "hello"              # then check Langfuse for a "Tchuekam turn" trace
```

## Optional tuning

```bash
TCHUEKAM_LANGFUSE_ENV=production       # environment tag
TCHUEKAM_LANGFUSE_RELEASE=v1.0.0       # release tag
TCHUEKAM_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
TCHUEKAM_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
TCHUEKAM_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
tchuekam plugins disable observability/langfuse
```
