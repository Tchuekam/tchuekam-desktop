import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { isStandaloneWebRoute, routeSessionId } from '@/app/routes'
import { DEFAULT_WEB_API_URL, resolveBackendOrigin } from '@/lib/platform'
import { installWebBridge } from '@/web/bridge'

describe('Web route & platform hardening', () => {
  const originalLocation = window.location

  function setHostname(url: string) {
    Object.defineProperty(window, 'location', {
      value: new URL(url),
      configurable: true,
      writable: true
    })
  }

  beforeEach(() => {
    delete (window as unknown as Record<string, unknown>).__HERMES_SESSION_TOKEN__
    delete (window as unknown as Record<string, unknown>).__HERMES_AUTH_REQUIRED__
    delete (window as unknown as Record<string, unknown>).__HERMES_BASE_PATH__
    setHostname('http://localhost:5173/')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      configurable: true,
      writable: true
    })
  })

  it('recognizes standalone web routes and decodes session route ids safely', () => {
    expect(isStandaloneWebRoute('/business')).toBe(true)
    expect(isStandaloneWebRoute('/mobile')).toBe(true)
    expect(isStandaloneWebRoute('/image-studio')).toBe(true)
    expect(isStandaloneWebRoute('/chat')).toBe(false)
    expect(isStandaloneWebRoute('/settings')).toBe(false)

    expect(routeSessionId('/session%20bad')).toBe('session bad')
    expect(routeSessionId('/%E0%A4%A')).toBe('%E0%A4%A')
    expect(routeSessionId('/settings')).toBeNull()
  })

  it('resolves backend origin accurately for hosted and backend-served domains', () => {
    setHostname('https://preview-app.vercel.app/')
    expect(resolveBackendOrigin()).toBe(DEFAULT_WEB_API_URL)

    setHostname('https://tchuekam-demo.netlify.app/')
    expect(resolveBackendOrigin()).toBe(DEFAULT_WEB_API_URL)

    setHostname('https://app.tchuekam.com/')
    expect(resolveBackendOrigin()).toBe(DEFAULT_WEB_API_URL)
    ;(window as unknown as Record<string, unknown>).__HERMES_AUTH_REQUIRED__ = true
    expect(resolveBackendOrigin()).toBe('')
  })

  it('handles HTML SPA fallback and malformed JSON errors cleanly in web bridge apiRequest', async () => {
    delete (window as unknown as Record<string, unknown>).hermesDesktop
    installWebBridge()

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    fetchMock.mockResolvedValueOnce(
      new Response('<!doctype html><html><body>SPA</body></html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' }
      })
    )

    await expect(
      window.hermesDesktop.api({ path: '/api/status', method: 'GET' })
    ).rejects.toThrow(/Expected JSON from .* got HTML/)

    fetchMock.mockResolvedValueOnce(
      new Response('{not-valid-json', {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    )

    await expect(
      window.hermesDesktop.api({ path: '/api/status', method: 'GET' })
    ).rejects.toThrow(/Invalid JSON response/)
  })
})
