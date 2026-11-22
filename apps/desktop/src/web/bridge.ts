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
import { getFreshSupabaseAccessToken } from '@/lib/supabase-auth'

const DEFAULT_FETCH_TIMEOUT_MS = 30_000
const SESSION_HEADER = 'X-Hermes-Session-Token'
const SECRET_STORAGE_PREFIX = 'tchuekam:secret:'
const uploadedImageDataUrls = new Map<string, string>()

function uint8ToDataUrl(data: ArrayBuffer | Uint8Array, mimeType: string): string {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data)
  let binary = ''
  const chunkSize = 0x8000

  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize))
  }

  return `data:${mimeType};base64,${btoa(binary)}`
}

async function uploadWebImageBytes(data: ArrayBuffer | Uint8Array, ext: string): Promise<string> {
  const cleanExt = ext.replace(/^\./, '').toLowerCase() || 'png'
  const mime =
    cleanExt === 'jpg' || cleanExt === 'jpeg'
      ? 'image/jpeg'
      : cleanExt === 'webp'
        ? 'image/webp'
        : cleanExt === 'gif'
          ? 'image/gif'
          : 'image/png'
  const dataUrl = uint8ToDataUrl(data, mime)
  const uploaded = await apiFetch<{ ok: boolean; path: string }>({
    path: '/api/uploads/image',
    method: 'POST',
    body: { data_url: dataUrl, filename: `upload-${Date.now()}.${cleanExt}` }
  })

  if (!uploaded?.path) {
    throw new Error('Backend did not return a path for the uploaded image.')
  }

  uploadedImageDataUrls.set(uploaded.path, dataUrl)

  return uploaded.path
}

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
  if (webConfig.apiUrl) {
    return webConfig.apiUrl
  }

  return `${window.location.origin.replace(/\/+$/, '')}${webConfig.basePath}`
}

/**
 * Build the gateway WebSocket URL, with whichever credential this deployment
 * authenticates by.
 *
 * Browsers cannot set headers on a WebSocket upgrade, so the credential rides
 * in the query string either way:
 *
 * - Gate off: `?token=` carrying the dashboard session token, as the desktop
 *   shell does.
 * - Gate on: `?ticket=` — single-use, 30-second TTL, minted against the
 *   session cookie. The session token is not injected at all in this mode and
 *   is rejected by the server even if one were supplied, so a ticket is the
 *   only way through. Minting per connection is the documented pattern.
 */
async function buildWsUrl(baseUrl: string): Promise<string> {
  const parsed = new URL(baseUrl)
  const scheme = parsed.protocol === 'https:' ? 'wss' : 'ws'
  const prefix = parsed.pathname.replace(/\/+$/, '')
  let query = ''

  if (webConfig.authRequired) {
    const minted = await apiFetch<{ ticket: string }>({
      path: '/api/auth/ws-ticket',
      method: 'POST'
    })

    query = `?ticket=${encodeURIComponent(minted.ticket)}`
  } else if (webConfig.token) {
    query = `?token=${encodeURIComponent(webConfig.token)}`
  }

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

  const supabaseToken = request.path.startsWith('/api/v1/') ? await getFreshSupabaseAccessToken() : null

  try {
    response = await fetch(url, {
      credentials: webConfig.authRequired ? 'include' : 'same-origin',
      method: request.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(webConfig.token ? { [SESSION_HEADER]: webConfig.token } : {}),
        ...(supabaseToken ? { Authorization: `Bearer ${supabaseToken}` } : {})
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

  try {
    return JSON.parse(text) as T
  } catch {
    throw new Error(`Invalid JSON response from ${url}`)
  }
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

async function connection(): Promise<HermesConnection> {
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
    wsUrl: await buildWsUrl(baseUrl),
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

