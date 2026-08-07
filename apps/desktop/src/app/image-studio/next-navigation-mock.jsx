import React from 'react'

export function useRouter() {
  return {
    push: (url) => {
      if (typeof window === 'undefined' || !url) return
      if (url.startsWith('http://') || url.startsWith('https://')) {
        if (window.hermesDesktop?.openExternal) {
          void window.hermesDesktop.openExternal(url)
        } else {
          window.open(url, '_blank', 'noopener,noreferrer')
        }
        return
      }
      const tabId = url.split('/studio/')[1] || url.split('tab=')[1]
      const isDesktopEnv = window.location.pathname.startsWith('/image-studio')
      const targetUrl = tabId
        ? (isDesktopEnv ? `/image-studio?tab=${tabId}` : `/studio/${tabId}`)
        : (isDesktopEnv ? window.location.pathname : url)
      window.history.pushState(null, '', targetUrl)
      window.dispatchEvent(new Event('popstate'))
    },
    replace: (url) => {
      if (typeof window === 'undefined' || !url) return
      if (url.startsWith('http://') || url.startsWith('https://')) {
        if (window.hermesDesktop?.openExternal) {
          void window.hermesDesktop.openExternal(url)
        } else {
          window.open(url, '_blank', 'noopener,noreferrer')
        }
        return
      }
      const tabId = url.split('/studio/')[1] || url.split('tab=')[1]
      const isDesktopEnv = window.location.pathname.startsWith('/image-studio')
      const targetUrl = tabId
        ? (isDesktopEnv ? `/image-studio?tab=${tabId}` : `/studio/${tabId}`)
        : (isDesktopEnv ? window.location.pathname : url)
      window.history.replaceState(null, '', targetUrl)
      window.dispatchEvent(new Event('popstate'))
    },
    prefetch: () => {},
    back: () => {
      if (typeof window !== 'undefined') window.history.back()
    },
    forward: () => {
      if (typeof window !== 'undefined') window.history.forward()
    },
    refresh: () => {}
  }
}

export function useParams() {
  return {}
}

export function usePathname() {
  if (typeof window !== 'undefined') {
    return window.location.hash.replace(/^#/, '') || '/'
  }
  return '/'
}

export function useSearchParams() {
  return new URLSearchParams()
}

export function redirect(url) {
  if (typeof window !== 'undefined') window.location.hash = url
}

export default {
  useRouter,
  useParams,
  usePathname,
  useSearchParams,
  redirect
}
