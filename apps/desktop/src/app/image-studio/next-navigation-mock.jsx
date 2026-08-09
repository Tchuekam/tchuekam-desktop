import React from 'react'

// The studio packages were written for Next's app router. The desktop shell
// renders a single route and uses react-router's HashRouter (see src/main.tsx),
// so the live route is `location.hash` — e.g. `#/image-studio?tab=design-agent`.
// The pathname is whatever the dev server or file:// happened to serve and is
// ignored by the router entirely.
//
// Two consequences drive this module:
//   1. All studio URL state (active tab, active session) must round-trip
//      through the hash query, or a reload loses it.
//   2. Writing `location.pathname` — which an earlier version of this shim did
//      — silently did nothing, and re-deriving "am I in the desktop shell?"
//      from that pathname was a one-way trap: the first `/studio/*` push made
//      the check false forever, so the shell could never route back.
//
// This file is aliased only by apps/desktop/vite.config.ts, so it always runs
// inside the desktop shell.
export const STUDIO_PATH = '/image-studio'

function readHash() {
  if (typeof window === 'undefined') {
    return { path: STUDIO_PATH, query: '' }
  }

  const raw = window.location.hash.replace(/^#/, '') || STUDIO_PATH
  const [path, query = ''] = raw.split('?')

  return { path: path || STUDIO_PATH, query }
}

// `tab` is desktop-shell state the studio components don't know about, so it
// survives a query rewrite unless the caller sets it explicitly.
function mergeQuery(incomingQuery) {
  const incoming = new URLSearchParams(incomingQuery)
  const merged = new URLSearchParams(readHash().query)

  for (const key of [...merged.keys()]) {
    if (key !== 'tab') {
      merged.delete(key)
    }
  }

  for (const [key, value] of incoming) {
    merged.set(key, value)
  }

  return merged
}

function buildHash(params) {
  const { path } = readHash()
  const base = path.startsWith(STUDIO_PATH) ? path : STUDIO_PATH
  const query = params.toString()

  return query ? `${base}?${query}` : base
}

// Translate a Next-style href into this app's hash route.
export function toDesktopHash(url) {
  // Query-only hrefs (`?session=<id>`) — the studio's main navigation idiom.
  if (url.startsWith('?')) {
    return buildHash(mergeQuery(url.slice(1)))
  }

  const [path, query = ''] = url.split('?')
  const tabId = url.split('/studio/')[1]?.split(/[?#]/)[0] || new URLSearchParams(query).get('tab')

  if (tabId) {
    const params = mergeQuery(query)

    params.set('tab', tabId)

    return buildHash(params)
  }

  // Routes like /canvas exist only in the Next app. Their intent is "start a
  // blank canvas", so stay on the current tab and drop the session rather than
  // navigating somewhere the desktop router cannot render.
  if (path && path !== '/') {
    const params = mergeQuery('')

    params.delete('session')

    return buildHash(params)
  }

  return buildHash(mergeQuery(query))
}

function isExternal(url) {
  return url.startsWith('http://') || url.startsWith('https://') || url.startsWith('mailto:')
}

export function openExternal(url) {
  if (typeof window === 'undefined') {
    return
  }

  if (window.hermesDesktop?.openExternal) {
    void window.hermesDesktop.openExternal(url)
  } else {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

export function navigate(url, mode) {
  if (typeof window === 'undefined' || !url) {
    return
  }

  if (isExternal(url)) {
    openExternal(url)

    return
  }

  const target = `#${toDesktopHash(url)}`

  if (window.location.hash === target) {
    return
  }

  if (mode === 'replace') {
    window.history.replaceState(null, '', target)
  } else {
    window.history.pushState(null, '', target)
  }

  // history.* never emits either event. HashRouter listens for hashchange; the
  // studio shell and the hooks below listen for popstate.
  window.dispatchEvent(new Event('hashchange'))
  window.dispatchEvent(new Event('popstate'))
}

// Re-render on any same-document navigation, however it was triggered.
function useHashLocation() {
  const [value, setValue] = React.useState(() =>
    typeof window === 'undefined' ? '' : window.location.hash
  )

  React.useEffect(() => {
    const sync = () => setValue(window.location.hash)

    window.addEventListener('popstate', sync)
    window.addEventListener('hashchange', sync)

    return () => {
      window.removeEventListener('popstate', sync)
      window.removeEventListener('hashchange', sync)
    }
  }, [])

  return value
}

export function useRouter() {
  return React.useMemo(
    () => ({
      back: () => {
        if (typeof window !== 'undefined') {
          window.history.back()
        }
      },
      forward: () => {
        if (typeof window !== 'undefined') {
          window.history.forward()
        }
      },
      prefetch: () => {},
      push: url => navigate(url, 'push'),
      refresh: () => {},
      replace: url => navigate(url, 'replace')
    }),
    []
  )
}

export function useParams() {
  return {}
}

export function usePathname() {
  useHashLocation()

  return readHash().path
}

// Returning a real, reactive URLSearchParams is load-bearing: the design agent
// reads its active conversation from `searchParams.get("session")`. The previous
// stub returned an empty set, so every session click silently reopened a blank
// canvas and the session was never restored on reload.
export function useSearchParams() {
  useHashLocation()

  const query = readHash().query

  return React.useMemo(() => new URLSearchParams(query), [query])
}

export function redirect(url) {
  navigate(url, 'replace')
}

export default {
  redirect,
  useParams,
  usePathname,
  useRouter,
  useSearchParams
}
