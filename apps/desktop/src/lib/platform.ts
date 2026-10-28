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
 * Hosted-build settings. Everything is read at build time, so a deploy swaps
 * these by rebuilding with different env vars.
 *
 * `apiUrl` empty means "same origin" — the right default when the agent
 * backend serves the bundle itself, or when a platform rewrite proxies
 * `/api/*` to it.
 */
export const webConfig = {
  apiUrl: String(env.VITE_HERMES_API_URL ?? '').replace(/\/+$/, ''),
  token: String(env.VITE_HERMES_TOKEN ?? ''),
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
