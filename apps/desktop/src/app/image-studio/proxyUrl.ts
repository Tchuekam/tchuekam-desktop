import { resolveBackendOrigin, webConfig } from '@/lib/platform'

export function resolveMuapiProxyBase(): string {
  const origin = resolveBackendOrigin()
  const basePath = origin ? '' : webConfig.basePath

  return `${origin}${basePath}/api/muapi-proxy`
}

export function rewriteMuapiProxyUrl(url: string): string {
  if (!url || typeof window === 'undefined' || !window.location?.protocol?.startsWith('http')) {
    return url
  }

  const base = resolveMuapiProxyBase()

  if (url.startsWith(`${base}/`) || url === base) {
    return url
  }

  if (url.startsWith('/api/api/v1/')) {
    return `${base}/api/v1/${url.slice('/api/api/v1/'.length)}`
  }

  if (url.startsWith('/api/workflow/')) {
    return `${base}/workflow/${url.slice('/api/workflow/'.length)}`
  }

  if (url.startsWith('/api/app/')) {
    return `${base}/app/${url.slice('/api/app/'.length)}`
  }

  if (url === '/api/agents' || url.startsWith('/api/agents/')) {
    return `${base}/agents${url.slice('/api/agents'.length)}`
  }

  if (url === '/api/v1/creative-agent' || url.startsWith('/api/v1/creative-agent/')) {
    return `${base}/api/v1/creative-agent${url.slice('/api/v1/creative-agent'.length)}`
  }

  if (url.startsWith('/api/v1/')) {
    return `${base}/api/v1/${url.slice('/api/v1/'.length)}`
  }

  return url
}

export function applyMuapiProxyRequest<
  T extends { url?: string; headers?: Record<string, string>; withCredentials?: boolean }
>(config: T): T {
  if (config.url) {
    config.url = rewriteMuapiProxyUrl(config.url)
  }

  if (webConfig.token) {
    config.headers = config.headers || {}
    config.headers['X-Hermes-Session-Token'] = webConfig.token
  }

  if (webConfig.authRequired) {
    config.withCredentials = true
  }

  return config
}

export function getMuapiFetchOptions(extraHeaders: Record<string, string> = {}): {
  credentials: RequestCredentials
  headers: Record<string, string>
} {
  const headers: Record<string, string> = {
    ...(webConfig.token ? { 'X-Hermes-Session-Token': webConfig.token } : {}),
    ...extraHeaders
  }

  const rawKey = headers['x-api-key'] ?? headers['X-Api-Key']

  if (!rawKey || rawKey === 'server-configured') {
    delete headers['x-api-key']
    delete headers['X-Api-Key']
  }

  return {
    credentials: webConfig.authRequired ? 'include' : 'same-origin',
    headers
  }
}
