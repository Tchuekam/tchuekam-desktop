import type { Session } from '@supabase/supabase-js'

const TRUSTED_HOSTS = new Set([
  'localhost',
  '127.0.0.1',
  'tchuekam.com',
  'www.tchuekam.com',
  'app.tchuekam.com',
  'auth.tchuekam.com',
  'portal.tchuekam.com',
  'tchuekam-agent-production.up.railway.app',
  'tchuekam-auth-production.up.railway.app',
])

export function isAllowedRedirectTarget(rawTarget?: string | null): boolean {
  if (!rawTarget) return false
  const trimmed = rawTarget.trim()
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) {
    return true
  }

  try {
    const parsed = new URL(trimmed)
    const configuredDesktop = process.env.NEXT_PUBLIC_DESKTOP_WEB_URL
    if (configuredDesktop) {
      const configuredHost = new URL(configuredDesktop).hostname.toLowerCase()
      TRUSTED_HOSTS.add(configuredHost)
    }
    const host = parsed.hostname.toLowerCase()
    const isHttpsOrLocal =
      parsed.protocol === 'https:' ||
      (parsed.protocol === 'http:' && (host === 'localhost' || host === '127.0.0.1'))
    return (
      isHttpsOrLocal &&
      (TRUSTED_HOSTS.has(host) || host.endsWith('.tchuekam.com'))
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
      const hashParams = new URLSearchParams()
      hashParams.set('access_token', session.access_token)
      if (session.refresh_token) hashParams.set('refresh_token', session.refresh_token)
      if (session.expires_at) hashParams.set('expires_at', String(session.expires_at))
      hashParams.set('token_type', session.token_type || 'bearer')
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
    if (isRemoteHost && (!configured || /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/i.test(configured))) {
      desktopBase = host.endsWith('.up.railway.app')
        ? 'https://tchuekam-agent-production.up.railway.app'
        : 'https://tchuekam.com'
    }
  }
  if (!desktopBase) return null
  const { url } = resolvePostAuthDestination(desktopBase, session)
  return url === '/' ? null : url
}
