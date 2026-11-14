import { useMediaQuery } from './use-media-query'

export const MOBILE_BREAKPOINT_PX = 768
export const COMPACT_BREAKPOINT_PX = 1024

export const MOBILE_MEDIA_QUERY = `(max-width: ${(MOBILE_BREAKPOINT_PX - 1) / 16}rem)`
export const COMPACT_MEDIA_QUERY = `(max-width: ${(COMPACT_BREAKPOINT_PX - 1) / 16}rem)`

export function isCompactViewport(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }

  return window.matchMedia(COMPACT_MEDIA_QUERY).matches
}

export const useIsMobile = () => useMediaQuery(MOBILE_MEDIA_QUERY)
export const useIsCompactViewport = () => useMediaQuery(COMPACT_MEDIA_QUERY)
