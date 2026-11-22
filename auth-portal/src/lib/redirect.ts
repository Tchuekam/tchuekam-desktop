import type { Session } from '@supabase/supabase-js'

const BASE_TRUSTED_HOSTS = [
  'tchuekam.com',
  'www.tchuekam.com',
  'app.tchuekam.com',
  'auth.tchuekam.com',
  'portal.tchuekam.com',
  'tchuekam-agent-production.up.railway.app',
  'tchuekam-auth-production.up.railway.app',
] as const

const CONTROL_CHARS_RE = /[\u0000-\u001f\u007f]/

function getAllowedHosts(): { trustedHosts: Set<string>; devLocalHosts: Set<string> } {
  const trustedHosts = new Set<string>(BASE_TRUSTED_HOSTS)
  const devLocalHosts = new Set<string>(
    process.env.NODE_ENV !== 'production' ? ['localhost', '127.0.0.1'] : []
  )
  const configuredDesktop = (process.env.NEXT_PUBLIC_DESKTOP_WEB_URL || '').trim()
  if (configuredDesktop) {
    try {
      const configuredHost = new URL(configuredDesktop).hostname.toLowerCase()
      if (configuredHost) {
        trustedHosts.add(configuredHost)
      }
    } catch {
      // Ignore malformed env URL
    }
  }
  return { trustedHosts, devLocalHosts }
}

export function isAllowedRedirectTarget(rawTarget?: string | null): boolean {
  if (!rawTarget) return false
  const trimmed = rawTarget.trim()
  if (!trimmed || CONTROL_CHARS_RE.test(trimmed) || trimmed.includes('\\')) {
    return false
  }
  if (trimmed.startsWith('/')) {
    return !trimmed.startsWith('//')
  }

  try {
    const parsed = new URL(trimmed)
    if (parsed.username || parsed.password) {
      return false
    }
    const host = parsed.hostname.toLowerCase()
    const { trustedHosts, devLocalHosts } = getAllowedHosts()

    const isAllowedLocalHttp =
      process.env.NODE_ENV !== 'production' &&
      parsed.protocol === 'http:' &&
      devLocalHosts.has(host)

    if (parsed.protocol !== 'https:' && !isAllowedLocalHttp) {
      return false
    }

    return (
      trustedHosts.has(host) ||
      devLocalHosts.has(host) ||
      host.endsWith('.tchuekam.com')
    )
  } catch {
    return false
  }
}

export function resolvePostAuthDestination(
  rawNext: string | null | undefined,
  session: Session | null
): { url: string; external: boolean } {
  const fallback = '/'
  if (!rawNext || !isAllowedRedirectTarget(rawNext)) {
    return { url: fallback, external: false }
  }

  const trimmed = rawNext.trim()
  if (trimmed.startsWith('/')) {
    return { url: trimmed, external: false }
  }

  try {
    const targetUrl = new URL(trimmed)
    const currentOrigin = typeof window !== 'undefined' ? window.location.origin : ''
    if (currentOrigin && targetUrl.origin === currentOrigin) {
      return { url: `${targetUrl.pathname}${targetUrl.search}${targetUrl.hash}`, external: false }
    }

    if (session?.access_token) {
      const existingReturnHash =
        targetUrl.searchParams.get('return_hash') ||
        (targetUrl.hash.startsWith('#/') ? targetUrl.hash : '')
      if (targetUrl.searchParams.has('return_hash')) {
        targetUrl.searchParams.delete('return_hash')
      }

      const hashParams = new URLSearchParams()
      hashParams.set('access_token', session.access_token)
      if (session.refresh_token) hashParams.set('refresh_token', session.refresh_token)
      if (session.expires_at) hashParams.set('expires_at', String(session.expires_at))
      hashParams.set('token_type', session.token_type || 'bearer')
      if (existingReturnHash && existingReturnHash.startsWith('#/')) {
        hashParams.set('return_hash', existingReturnHash)
      }
      targetUrl.hash = hashParams.toString()
    }

    return { url: targetUrl.toString(), external: true }
  } catch {
    return { url: fallback, external: false }
  }
}

export function getDesktopLaunchUrl(session: Session | null): string | null {
  const configured = (process.env.NEXT_PUBLIC_DESKTOP_WEB_URL || '').trim()
  let desktopBase = configured
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    const isRemoteHost = host !== '' && host !== 'localhost' && host !== '127.0.0.1'
    if (
      isRemoteHost &&
      (!configured || /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/i.test(configured))
    ) {
      desktopBase = host.endsWith('.up.railway.app')
        ? 'https://tchuekam-agent-production.up.railway.app'
        : 'https://tchuekam.com'
    }
  }
  if (!desktopBase) return null
  const { url } = resolvePostAuthDestination(desktopBase, session)
  return url === '/' ? null : url
}
