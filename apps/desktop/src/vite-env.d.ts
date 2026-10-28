/// <reference types="vite/client" />

/**
 * True in the hosted web bundle, false in the Electron renderer. Injected as a
 * Vite `define` constant by both configs so the unused shell's code paths are
 * dropped at build time. See src/lib/platform.ts.
 */
declare const __HERMES_WEB__: boolean

interface ImportMetaEnv {
  /** Base URL of the TchuekaM agent backend. Empty means same origin. */
  readonly VITE_HERMES_API_URL?: string
  /** Dashboard session token (HERMES_DASHBOARD_SESSION_TOKEN on the server). */
  readonly VITE_HERMES_TOKEN?: string
  /** Version string shown in the web build's About panel. */
  readonly VITE_HERMES_APP_VERSION?: string
  /** '0' to unlock host-management surfaces in the web build. Default '1'. */
  readonly VITE_HERMES_DEMO?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
