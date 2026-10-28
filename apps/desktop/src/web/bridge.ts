/**
 * Browser implementation of the `window.hermesDesktop` bridge.
 *
 * The renderer was written against an Electron preload that proxies to the
 * main process (see electron/preload.cjs). The hosted web build has no main
 * process, so this module provides the same shape backed by `fetch`, the
 * WebSocket the gateway client opens itself, and standard browser APIs.
 *
 * Capabilities that need a real machine — a PTY, the filesystem, native
 * dialogs, the in-place updater, first-run bootstrap — have no browser
 * equivalent. Those reject with `unsupported()` rather than resolving with
 * something plausible, so a caller that slips past a UI guard fails loudly in
 * the console instead of silently doing nothing.
 */
import type {
  BackendExit,
  DesktopBootProgress,
  DesktopBootstrapState,
  DesktopConnectionConfig,
  DesktopUpdateStatus,
  DesktopVersionInfo,
  HermesApiRequest,
  HermesConnection,
  HermesNotification,
  HermesPreviewFileChanged,
  HermesReadDirResult,
  HermesReadFileTextResult,
  HermesSelectPathsOptions
} from '@/global'
import { webConfig } from '@/lib/platform'

const DEFAULT_FETCH_TIMEOUT_MS = 30_000
const SESSION_HEADER = 'X-Hermes-Session-Token'

/** Shape of the preload bridge, derived from the ambient Window declaration. */
type DesktopBridge = Window['hermesDesktop']

/** No-op unsubscribe for the event hooks the browser has nothing to emit on. */
const noopUnsubscribe = () => () => undefined

function unsupported(feature: string): never {
  throw new Error(`${feature} is not available in the TchuekaM web app.`)
}

/**
 * Backend origin for this build.
 *
 * Empty `apiUrl` means same origin, which covers both the agent backend
 * serving the bundle directly and a host-level rewrite proxying `/api/*`.
 */
function resolveBaseUrl(): string {
  return webConfig.apiUrl || window.location.origin.replace(/\/+$/, '')
}

/**
 * The gateway WebSocket cannot carry an Authorization header — browsers do not
 * allow headers on the upgrade — so the backend reads the dashboard session
 * token from the query string, exactly as the desktop shell does.
 */
function buildWsUrl(baseUrl: string, token: string): string {
  const parsed = new URL(baseUrl)
  const scheme = parsed.protocol === 'https:' ? 'wss' : 'ws'
  const prefix = parsed.pathname.replace(/\/+$/, '')
  const query = token ? `?token=${encodeURIComponent(token)}` : ''

  return `${scheme}://${parsed.host}${prefix}/api/ws${query}`
}

/**
 * Mirrors fetchJson() in electron/main.cjs, including its HTML guard: a 2xx
 * body that starts with a doctype means the request fell through to the SPA
 * index instead of hitting an API route, and `JSON.parse` would report that as
 * an opaque "Unexpected token '<'".
 */
async function apiFetch<T>(request: HermesApiRequest): Promise<T> {
  const baseUrl = resolveBaseUrl()
  const url = `${baseUrl}${request.path}`
  const timeoutMs = Number(request.timeoutMs) > 0 ? Number(request.timeoutMs) : DEFAULT_FETCH_TIMEOUT_MS
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  let response: Response

  try {
    response = await fetch(url, {
      method: request.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(webConfig.token ? { [SESSION_HEADER]: webConfig.token } : {})
      },
      body: request.body === undefined ? undefined : JSON.stringify(request.body),
      signal: controller.signal
    })
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`Request to ${request.path} timed out after ${timeoutMs}ms`)
    }

    throw error
  } finally {
    clearTimeout(timer)
  }

  const text = await response.text()

  if (!response.ok) {
    throw new Error(`${response.status}: ${text || response.statusText}`)
  }

  if (!text) {
    return null as T
  }

  const looksHtml = /^\s*<(?:!doctype|html)/i.test(text)

  if (looksHtml || (response.headers.get('content-type') || '').includes('text/html')) {
    throw new Error(
      `Expected JSON from ${url} but got HTML (status ${response.status}). ` +
        'The endpoint is likely missing on the TchuekaM backend.'
    )
  }

  return JSON.parse(text) as T
}

/** The web build is always "booted" — there is no local backend to start. */
function bootProgress(): DesktopBootProgress {
  return {
    error: null,
    fakeMode: false,
    message: 'Connected',
    phase: 'backend.ready',
    progress: 100,
    running: false,
    timestamp: Date.now()
  }
}

function connection(): HermesConnection {
  const baseUrl = resolveBaseUrl()

  return {
    baseUrl,
    // Browser chrome owns the window, so the renderer's macOS traffic-light
    // inset and fullscreen padding are always zero here.
    isFullscreen: false,
    mode: 'remote',
    nativeOverlayWidth: 0,
    source: 'env',
    token: webConfig.token,
    wsUrl: buildWsUrl(baseUrl, webConfig.token),
    logs: [],
    windowButtonPosition: null
  }
}

function connectionConfig(): DesktopConnectionConfig {
  return {
    // Baked in at build time, so the Gateway settings panel must not offer to
    // edit it — `envOverride` is the flag that panel already reads to go
    // read-only.
    envOverride: true,
    mode: 'remote',
    remoteTokenPreview: webConfig.token ? `${webConfig.token.slice(0, 4)}…` : null,
    remoteTokenSet: Boolean(webConfig.token),
    remoteUrl: resolveBaseUrl()
  }
}

/** Trigger a browser download for a URL or blob, the web stand-in for "save". */
function download(url: string, filename?: string): void {
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || ''
  anchor.rel = 'noopener'
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
}

const bridge: DesktopBridge = {
  getConnection: async () => connection(),
  getBootProgress: async () => bootProgress(),
  getConnectionConfig: async () => connectionConfig(),
  saveConnectionConfig: async () => connectionConfig(),
  applyConnectionConfig: async () => connectionConfig(),
  testConnectionConfig: async () => {
    const status = await apiFetch<{ version?: string }>({ path: '/api/status' })

    return { ok: true, baseUrl: resolveBaseUrl(), version: status?.version ?? null }
  },

  api: apiFetch,

  notify: async (payload: HermesNotification) => {
    if (!('Notification' in window)) {
      return false
    }

    // Asking on first use keeps the permission prompt tied to something the
    // visitor just did, rather than firing on page load.
    const permission =
      Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission

    if (permission !== 'granted') {
      return false
    }

    new Notification(payload?.title || 'TchuekaM', {
      body: payload?.body || '',
      silent: Boolean(payload?.silent)
    })

    return true
  },

  requestMicrophoneAccess: async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      // Release the device immediately — this call only answers "may we?",
      // the recorder opens its own stream when the user starts speaking.
      stream.getTracks().forEach(track => track.stop())

      return true
    } catch {
      return false
    }
  },

  // --- Filesystem: no browser equivalent -----------------------------------
  readFileDataUrl: async (): Promise<string> => unsupported('Reading local files'),
  readFileText: async (): Promise<HermesReadFileTextResult> => unsupported('Reading local files'),
  readDir: async (): Promise<HermesReadDirResult> => ({ entries: [], error: 'Not available in the web app.' }),
  gitRoot: async () => null,
  selectPaths: async (_options?: HermesSelectPathsOptions) => [],
  getPathForFile: () => '',

  writeClipboard: async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)

      return true
    } catch {
      return false
    }
  },

  saveImageFromUrl: async (url: string) => {
    download(url)

    return true
  },

  saveImageBuffer: async (data: ArrayBuffer | Uint8Array, ext: string) => {
    const blob = new Blob([data as BlobPart], { type: `image/${ext.replace(/^\./, '') || 'png'}` })
    const url = URL.createObjectURL(blob)
    const filename = `tchuekam-${Date.now()}.${ext.replace(/^\./, '') || 'png'}`

    download(url, filename)
    // Revoke on the next tick: revoking synchronously races the download the
    // click above just queued.
    setTimeout(() => URL.revokeObjectURL(url), 10_000)

    return filename
  },

  saveClipboardImage: async (): Promise<string> => unsupported('Saving the clipboard image'),

  // --- Preview rail --------------------------------------------------------
  // The desktop rail previews local files and localhost dev servers. In a
  // browser both of those point at the visitor's own machine rather than the
  // agent's, so there is nothing meaningful to resolve.
  normalizePreviewTarget: async () => null,
  watchPreviewFile: async () => ({ id: '', path: '' }),
  stopPreviewFileWatch: async () => false,
  onPreviewFileChanged: noopUnsubscribe as (
    callback: (payload: HermesPreviewFileChanged) => void
  ) => () => void,

  // --- Window chrome: owned by the browser ---------------------------------
  setTitleBarTheme: () => undefined,
  setPreviewShortcutActive: () => undefined,

  openExternal: async (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  },

  openImageStudioWindow: async () => {
    // No second BrowserWindow to open; the studio renders in the main view.
    return { ok: false }
  },

  fetchLinkTitle: async () => '',

  settings: {
    getDefaultProjectDir: async () => ({ defaultLabel: 'Server working directory', dir: null }),
    setDefaultProjectDir: async () => ({ dir: null }),
    pickDefaultProjectDir: async () => ({ canceled: true, dir: null })
  },

  revealLogs: async () => ({ ok: false, path: '', error: 'Not available in the web app.' }),
  getRecentLogs: async () => ({ path: '', lines: [] }),

  // --- Terminal: needs a PTY on the host -----------------------------------
  terminal: {
    dispose: async () => false,
    resize: async () => false,
    start: async () => unsupported('The terminal'),
    write: async () => false,
    onData: noopUnsubscribe as (id: string, callback: (payload: string) => void) => () => void,
    onExit: noopUnsubscribe as DesktopBridge['terminal']['onExit']
  },

  // --- Lifecycle events the browser never fires ----------------------------
  onClosePreviewRequested: noopUnsubscribe as (callback: () => void) => () => void,
  onOpenUpdatesRequested: noopUnsubscribe as (callback: () => void) => () => void,
  onWindowStateChanged: noopUnsubscribe as DesktopBridge['onWindowStateChanged'],
  onBackendExit: noopUnsubscribe as (callback: (payload: BackendExit) => void) => () => void,
  onBootProgress: callback => {
    // Resolve the boot overlay on the next tick. Calling back synchronously
    // would run before the subscriber has finished mounting.
    const timer = setTimeout(() => callback(bootProgress()), 0)

    return () => clearTimeout(timer)
  },

  // --- First-run bootstrap: desktop-install only ---------------------------
  getBootstrapState: async (): Promise<DesktopBootstrapState> => ({
    active: false,
    manifest: null,
    stages: {},
    error: null,
    log: [],
    startedAt: null,
    completedAt: null,
    unsupportedPlatform: null
  }),
  resetBootstrap: async () => ({ ok: false }),
  repairBootstrap: async () => ({ ok: false }),
  cancelBootstrap: async () => ({ ok: false, cancelled: false }),
  onBootstrapEvent: noopUnsubscribe as DesktopBridge['onBootstrapEvent'],

  getVersion: async (): Promise<DesktopVersionInfo> => ({
    appVersion: webConfig.version,
    electronVersion: '',
    nodeVersion: '',
    platform: 'web',
    hermesRoot: ''
  }),

  // --- Updates: the host redeploys, the page just reloads ------------------
  updates: {
    check: async (): Promise<DesktopUpdateStatus> => ({
      supported: false,
      reason: 'web',
      message: 'The web app updates when it is redeployed. Reload the page to pick up a new version.'
    }),
    apply: async () => ({ ok: false, error: 'Not available in the web app.' }),
    getBranch: async () => ({ branch: '' }),
    setBranch: async () => ({ branch: '' }),
    onProgress: noopUnsubscribe as DesktopBridge['updates']['onProgress']
  }
}

/**
 * Install the bridge before any renderer module reads it.
 *
 * Idempotent, and it never overwrites a real preload — if this bundle is ever
 * loaded inside Electron, the native bridge wins.
 */
export function installWebBridge(): void {
  if (window.hermesDesktop) {
    return
  }

  if (!webConfig.apiUrl) {
    // Same-origin only works when the agent backend serves this bundle
    // itself. On a static host it means every API call lands on the SPA
    // fallback and comes back as HTML.
    console.warn(
      '[tchuekam] VITE_HERMES_API_URL is not set — falling back to this origin. ' +
        'Set it to the TchuekaM backend URL unless that backend is serving this page.'
    )
  }

  window.hermesDesktop = bridge
}
