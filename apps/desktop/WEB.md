# TchuekaM Web

The same renderer as the desktop app, running in a browser against a hosted
backend. No install, no download — share a URL and people can use it.

## How it differs from the desktop app

The desktop renderer never talks to the backend directly. It calls
`window.hermesDesktop`, a bridge that Electron's preload exposes and the main
process implements (`electron/preload.cjs` → `electron/main.cjs`). The web
build keeps the renderer and replaces only that bridge, with one backed by
`fetch` and `WebSocket` (`src/web/bridge.ts`, installed by `src/web/main.tsx`
before anything else loads).

So the chat, sessions, skills, artifacts, agents, business hub and image studio
all work unchanged. What cannot cross into a browser is anything that needs a
real machine:

| Capability | Web build |
|---|---|
| Chat, sessions, streaming, tool activity | Works |
| Skills, artifacts, agents, business hub, image studio | Works |
| Voice input | Works (asks for the mic) |
| Terminal | Not available — needs a PTY |
| File browser, local file attachments | Not available — needs filesystem access |
| Preview rail | Not available — it resolves paths on the agent's host |
| Settings, profiles, messaging, automation | Hidden in demo mode (see below) |
| In-place updates, first-run install | Not applicable — redeploy and reload |

`src/lib/platform.ts` holds the flags (`IS_WEB`, `IS_LOCKED_DEMO`,
`HAS_NATIVE_FS`). They are compile-time constants, so each build drops the
other shell's code.

## Demo mode

`VITE_HERMES_DEMO=1` (the default) hides every surface that configures the
deployment rather than the conversation: settings, profiles, messaging and
automation, plus the terminal and file browser.

**Hiding the UI is not the security boundary.** The agent still has whatever
tools the backend gives it, and a visitor can simply ask for them in chat. A
public deployment must disable the dangerous toolsets server-side, in the
backend's `config.yaml`:

```yaml
tools:
  cli:
    disabled:
      - terminal
      - file
      - code_execution
      - delegation
      - cronjob
      - messaging
```

Also worth setting before a public demo: a spend cap on the model API key, and
a rate limit in front of the backend.

## Local development

```bash
npm run dev:web --workspace apps/desktop
```

It serves on <http://127.0.0.1:5175> and reads `apps/desktop/.env.local` —
copy `.env.web.example` to start. Point `VITE_HERMES_API_URL` at a running
backend:

```bash
hermes dashboard --no-open --tui --host 127.0.0.1 --port 9119
```

## Build

```bash
npm run build:web --workspace apps/desktop
```

Output lands in `apps/desktop/dist-web/`, a static site.

## Deploying

The frontend is static and the backend is a long-running Python process, so
they are two separate deployments.

### Frontend

`vercel.json` at the repo root already has the build command, output directory
and SPA fallback. Set the environment variables from `.env.web.example` in the
project settings.

Any static host works — the only requirement is serving `index.html` for
unknown paths.

### Backend

The agent backend is the root `Dockerfile` (not `Dockerfile.backend`, which
builds the separate `tchuekam_backend` auth API). Run it with no command and
`docker/main-wrapper.sh` already starts the right thing:

```
hermes dashboard --host 0.0.0.0 --port $PORT --insecure --no-open
```

Environment variables it needs:

- `HERMES_DASHBOARD_SESSION_TOKEN` — the same value as `VITE_HERMES_TOKEN`.
- `HERMES_DASHBOARD_ALLOWED_ORIGINS` — the frontend's origin, e.g.
  `https://your-app.vercel.app`. `*.vercel.app`, `*.netlify.app`,
  `*.up.railway.app` and `*.tchuekam.com` are already allowed by default, so
  this is only needed for a custom domain.
- A model provider key, e.g. `OPENROUTER_API_KEY`.

`--insecure` skips the dashboard's OAuth gate, which is what lets the session
token authenticate the WebSocket. It means the backend has no robust auth of
its own — disabling the dangerous toolsets above is what makes that acceptable.

Sessions and memory live in SQLite under `HERMES_HOME`. Mount a volume there,
or accept that a redeploy starts everyone fresh.

### Why no /api proxy

The frontend addresses the backend by absolute URL rather than proxying
`/api/*` through the frontend host. Host-level rewrites forward HTTP but not
WebSocket upgrades, and the gateway is a WebSocket. Cross-origin is handled by
CORS on the backend.
