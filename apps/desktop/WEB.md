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

### Known gap: Image Studio's Design Agent tab

Image generation works — `MuapiClient` calls `https://api.muapi.ai` directly in
a production build. The Design Agent tab (`#/image-studio?tab=design-agent`)
does not. Its vendored code picks its base URL from the page protocol:

```js
const DIRECT_UPSTREAM =
  typeof window === "undefined" || !window.location?.protocol?.startsWith("http")
```

Under Electron the page is `file://`, so it calls muapi directly. On the web it
is `https://`, so it falls back to same-origin `/api/v1/creative-agent` —
expecting the Next.js route handlers that proxied to muapi and swapped the
Bearer token for muapi's `x-api-key` header. Nothing serves those paths on a
static host, so the requests land on the SPA fallback and come back as HTML.

Two consequences:

- The Design Agent tab is broken in the web build. Fixing it means either
  calling muapi directly from the browser (which the dev-server proxy exists to
  avoid, partly for CORS) or standing up a real proxy route.
- **Do not mount anything public at `/api/v1/*` on this domain.** Those
  requests would then reach a real service instead of the fallback, and get
  confidently wrong answers rather than an obvious failure.

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

`vercel.json` at the repo root deploys the frontends as one Vercel project
using services:

| Service | Root | Public path |
|---|---|---|
| `desktop` | repo root (npm workspace) | `/` — everything not matched above |
| `website` | `website/` | `/docs/*` |

Set the environment variables from `.env.web.example` in the project settings.
They are read at build time, so changing one needs a redeploy.

The `desktop` service builds from the repo root rather than `apps/desktop`,
because the renderer resolves React from the workspace root's `node_modules`
(see `vite.aliases.ts`) — an install scoped to `apps/desktop` alone would not
hoist it.

The `website` service builds with `build:vercel`, which stages the Docusaurus
output under `build-vercel/docs/`. A service rewrite forwards the matched path
unchanged, and `docusaurus.config.ts` sets `baseUrl: '/docs/'`, so the files
have to sit at the path the generated HTML already points at. If the docs ever
move to their own domain, set `baseUrl` back to `/` and drop the staging step.

Any static host works for the app on its own — the only requirement is serving
`index.html` for unknown paths.

There are no service bindings. Bindings inject an internal URL into a calling
service at runtime, and nothing here calls another service from the server: the
only cross-service traffic is the browser talking to the agent backend, which
needs a public URL it can reach directly, and which is baked into the bundle at
build time.

### Backend

The agent backend runs from the repo root `Dockerfile` (not
`Dockerfile.backend`, which builds the separate `tchuekam_backend` auth API).
`render.yaml` at the repo root describes it as a Render service.

It needs a container with a disk, and cannot move to a serverless platform:
`HERMES_HOME` holds `state.db` (sessions, memory, FTS5 search), a
conversation's running agent lives in the process that owns its WebSocket, and
one turn can run for minutes. The blueprint mounts a disk at `/opt/data` for
exactly that reason — without it, every redeploy wipes every session.

Environment variables:

- `HERMES_DASHBOARD_ALLOWED_ORIGINS` — the web app's origin, if it is served
  from a different host than this service. Same-origin needs no entry.
- `HERMES_DASHBOARD_OAUTH_CLIENT_ID` / `HERMES_DASHBOARD_PORTAL_URL` — the
  dashboard auth gate's provider. See **Authentication** below.
- A model provider key, e.g. `OPENROUTER_API_KEY`. Put a spend cap on it.

Note that the Render disk mounts root-owned while the container runs as uid
10000, so check write permissions on the first deploy.

### Authentication

The dashboard engages an OAuth gate on any non-loopback bind unless
`--insecure` is passed. The gate is the production path: cookie sessions, a
login page, single-use 30-second WebSocket tickets, and an audit log.

**The gate requires the app and the backend to share an origin.** Session
cookies are set `SameSite=Lax` (`hermes_cli/dashboard_auth/cookies.py`), and a
Lax cookie is not sent on cross-site `fetch` or WebSocket handshakes. A bundle
served from another host would fail every authenticated call, including the
`POST /api/auth/ws-ticket` the gateway needs. Setting `SameSite=None` instead
trades that for third-party-cookie blocking in Safari and Chrome.

The image already does this. A `webapp_builder` stage in the root `Dockerfile`
builds `apps/desktop`'s browser bundle and copies the static output to
`/opt/hermes/web-app`, which `HERMES_WEB_DIST` points at — so the Render
service serves the app from its own origin. Only the built files cross stages,
so no Electron toolchain reaches the runtime image, and the runtime
`node_modules` tree (which deliberately omits `apps/*`) is untouched.

Build args let a deploy override the bundle's configuration:
`VITE_HERMES_API_URL` (empty = same origin), `VITE_HERMES_DEMO`,
`VITE_HERMES_APP_VERSION`.

When it serves the page, the dashboard injects three globals into `index.html`,
and the bundle prefers them over anything baked in at build time:

| Global | Used for |
|---|---|
| `__HERMES_SESSION_TOKEN__` | `/api/*` and the gateway `?token=`. Minted per process, so a build-time copy goes stale on restart — which is why the injected value wins. |
| `__HERMES_BASE_PATH__` | Serving under a reverse-proxy sub-path (`X-Forwarded-Prefix`). |
| `__HERMES_AUTH_REQUIRED__` | Gate on. No token is injected and the server rejects one, so the WebSocket mints a single-use ticket from `POST /api/auth/ws-ticket` per connection instead. |

This is why a same-origin deploy needs no `VITE_HERMES_TOKEN`: leaving it unset
is correct, and setting it would only supply a fallback for a split-origin
deployment.

The only bundled provider is `nous` (Nous Research Portal), under
`plugins/dashboard_auth/nous/`. Any other identity source needs a provider
plugin implementing `DashboardAuthProvider` (`hermes_cli/dashboard_auth/base.py`):
`start_login`, `complete_login`, `verify_session`, `refresh_session`,
`revoke_session`.

`--insecure` skips the gate entirely and falls back to a shared session token.
That token ships inside the JavaScript bundle, so anyone who opens the page can
read it and drive the agent on your API credits. It is acceptable for a
throwaway demo on a locked-down toolset; it is not an authentication system.

### Why no /api proxy

The frontend addresses the backend by absolute URL rather than proxying
`/api/*` through the frontend host. Host-level rewrites forward HTTP but not
WebSocket upgrades, and the gateway is a WebSocket. Cross-origin is handled by
CORS on the backend.
