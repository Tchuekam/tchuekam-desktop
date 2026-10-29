/**
 * Which shell is this bundle running in?
 *
 * The renderer is shared between the Electron desktop app and the hosted web
 * build. `__HERMES_WEB__` is a Vite `define` constant — statically `false` in
 * the desktop config, so every web-only branch is tree-shaken out of the
 * packaged app and vice versa.
 */
export const IS_WEB: boolean = __HERMES_WEB__
export const IS_DESKTOP = !IS_WEB

const env = import.meta.env

function envFlag(value: unknown, fallback: boolean): boolean {
  if (value === undefined || value === '') {
    return fallback
  }

  return value === '1' || value === 'true'
}

/**
 * Values the dashboard injects into index.html when it serves the bundle
 * itself (`_serve_index` in hermes_cli/web_server.py).
 *
 * These only exist on the same-origin deployment, and they beat anything baked
 * in at build time: the session token is minted per process, so a build-time
 * copy would be stale the moment the server restarts. Absent when the bundle
 * is served by a static host, which is why each read falls back.
 */
interface InjectedDashboardGlobals {
  __HERMES_SESSION_TOKEN__?: string
  __HERMES_BASE_PATH__?: string
  __HERMES_AUTH_REQUIRED__?: boolean
}

function injected(): InjectedDashboardGlobals {
  if (typeof window === 'undefined') {
    return {}
  }

  return window as unknown as InjectedDashboardGlobals
}

/**
 * Hosted-build settings.
 *
 * `apiUrl` empty means "same origin" — the right default when the agent
 * backend serves the bundle itself, which is also the only arrangement where
 * the auth gate's SameSite=Lax cookies reach it.
 */
export const webConfig = {
  apiUrl: String(env.VITE_HERMES_API_URL ?? '').replace(/\/+$/, ''),
  /**
   * Dashboard session token, used on `/api/*` and as `?token=` on the gateway
   * WebSocket. Injected by the server when it serves this page; the build-time
   * value is the fallback for a split-origin deployment.
   *
   * Empty when the auth gate is on — the gate authenticates by cookie, and the
   * WebSocket uses a single-use ticket instead.
   */
  get token(): string {
    return String(injected().__HERMES_SESSION_TOKEN__ ?? env.VITE_HERMES_TOKEN ?? '')
  },
  /**
   * Path prefix when served behind a reverse proxy that mounts the dashboard
   * under a sub-path (`X-Forwarded-Prefix`). Empty at a domain root.
   */
  get basePath(): string {
    return String(injected().__HERMES_BASE_PATH__ ?? '').replace(/\/+$/, '')
  },
  /**
   * True when the dashboard's OAuth gate is engaged. The WebSocket then needs
   * a ticket from `POST /api/auth/ws-ticket` rather than the session token.
   */
  get authRequired(): boolean {
    return injected().__HERMES_AUTH_REQUIRED__ === true
  },
  version: String(env.VITE_HERMES_APP_VERSION ?? 'web'),
  /**
   * Demo mode hides every surface that manages the host it runs on —
   * settings, credentials, profiles, automation, the terminal and the file
   * browser. On by default for the web build: a public deployment is shared
   * infrastructure, and those screens act on the server, not on the visitor.
   */
  demo: envFlag(env.VITE_HERMES_DEMO, true)
}

/** True when a host-management surface should be hidden from this build. */
export const IS_LOCKED_DEMO = IS_WEB && webConfig.demo

/**
 * The browser has no PTY and no filesystem handle, so the terminal pane and
 * file tree cannot work in the web build regardless of demo mode.
 */
export const HAS_NATIVE_FS = IS_DESKTOP
