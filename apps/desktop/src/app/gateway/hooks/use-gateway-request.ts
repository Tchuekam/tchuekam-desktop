import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useRef } from 'react'

import type { HermesGateway } from '@/hermes'
import { IS_WEB } from '@/lib/platform'
import { $gatewayState, setConnection } from '@/store/session'

function maybeRedirectToLoginFromError(error: unknown): boolean {
  if (!IS_WEB || typeof window === 'undefined') {
    return false
  }

  const msg = error instanceof Error ? error.message : String(error ?? '')

  if (!msg.startsWith('401:') && !msg.includes('401')) {
    return false
  }

  try {
    const jsonStart = msg.indexOf('{')

    if (jsonStart !== -1) {
      const body = JSON.parse(msg.slice(jsonStart)) as { login_url?: unknown }

      if (typeof body.login_url === 'string' && body.login_url) {
        window.location.assign(body.login_url)

        return true
      }
    }
  } catch {
    // Ignore parse failures on non-JSON 401 messages
  }

  return false
}

export function useGatewayRequest() {
  const gatewayState = useStore($gatewayState)
  const gatewayRef = useRef<HermesGateway | null>(null)

  const connectionRef = useRef<Awaited<ReturnType<NonNullable<typeof window.hermesDesktop>['getConnection']>> | null>(
    null
  )

  const gatewayStateRef = useRef(gatewayState)
  const reconnectingRef = useRef<Promise<HermesGateway | null> | null>(null)

  useEffect(() => {
    gatewayStateRef.current = gatewayState
  }, [gatewayState])

  const ensureGatewayOpen = useCallback(async () => {
    const existing = gatewayRef.current

    if (!existing) {
      return null
    }

    if (gatewayStateRef.current === 'open') {
      return existing
    }

    if (reconnectingRef.current) {
      return reconnectingRef.current
    }

    reconnectingRef.current = (async () => {
      const desktop = window.hermesDesktop

      if (!desktop) {
        return null
      }

      try {
        const conn = await desktop.getConnection()
        connectionRef.current = conn
        setConnection(conn)
        await existing.connect(conn.wsUrl)

        return existing
      } catch (err) {
        maybeRedirectToLoginFromError(err)
        connectionRef.current = null
        setConnection(null)

        return null
      } finally {
        reconnectingRef.current = null
      }
    })()

    return reconnectingRef.current
  }, [])

  const requestGateway = useCallback(
    async <T>(method: string, params: Record<string, unknown> = {}) => {
      const gateway = gatewayRef.current

      if (!gateway) {
        throw new Error('TchuekaM gateway unavailable')
      }

      try {
        return await gateway.request<T>(method, params)
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)

        if (!/not connected|connection closed/i.test(message)) {
          throw error
        }

        const recovered = await ensureGatewayOpen()

        if (!recovered) {
          throw error
        }

        return recovered.request<T>(method, params)
      }
    },
    [ensureGatewayOpen]
  )

  return { connectionRef, gatewayRef, requestGateway }
}
