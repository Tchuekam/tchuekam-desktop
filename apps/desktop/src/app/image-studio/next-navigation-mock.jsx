import React from 'react'

export function useRouter() {
  return {
    push: (url) => {
      if (typeof window !== 'undefined') window.location.hash = url
    },
    replace: (url) => {
      if (typeof window !== 'undefined') window.location.hash = url
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
