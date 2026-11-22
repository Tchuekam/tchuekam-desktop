import { useEffect, useRef } from 'react'

import type { HermesConnection } from '@/global'
import { HermesGateway } from '@/hermes'
import { IS_WEB } from '@/lib/platform'
import {
  $desktopBoot,
  applyDesktopBootProgress,
  completeDesktopBoot,
  failDesktopBoot,
  setDesktopBootStep
} from '@/store/boot'
import { setGateway } from '@/store/gateway'
import { notify, notifyError } from '@/store/notifications'
import { $connection, setConnection, setGatewayState, setSessionsLoading } from '@/store/session'
import type { RpcEvent } from '@/types/hermes'

interface GatewayBootOptions {
  handleGatewayEvent: (event: RpcEvent) => void
  onConnectionReady: (
    connection: Awaited<ReturnType<NonNullable<typeof window.hermesDesktop>['getConnection']>> | null
  ) => void
  onGatewayReady: (gateway: HermesGateway | null) => void
  refreshHermesConfig: () => Promise<void>
  refreshSessions: () => Promise<void>
}

export function useGatewayBoot({
  handleGatewayEvent,
  onConnectionReady,
  onGatewayReady,
  refreshHermesConfig,
  refreshSessions
}: GatewayBootOptions) {
  const callbacksRef = useRef({
    handleGatewayEvent,
    onConnectionReady,
    onGatewayReady,
    refreshHermesConfig,
    refreshSessions
  })

  callbacksRef.current = {
    handleGatewayEvent,
    onConnectionReady,
    onGatewayReady,
    refreshHermesConfig,
    refreshSessions
  }

  useEffect(() => {
    let cancelled = false
    const desktop = window.hermesDesktop

    const publish = (next: HermesConnection | null) => {
      callbacksRef.current.onConnectionReady(next)
      setConnection(next)
    }

    if (!desktop) {
      failDesktopBoot('Desktop IPC bridge is unavailable.')
      setSessionsLoading(false)

      return () => void (cancelled = true)
    }

    const offBootProgress = desktop.onBootProgress(payload => applyDesktopBootProgress(payload))
    void desktop
      .getBootProgress()
      .then(snapshot => applyDesktopBootProgress(snapshot))
      .catch(() => undefined)

    setDesktopBootStep({
      phase: 'renderer.boot',
      message: 'Starting desktop connection',
      progress: 6
    })

    const gateway = new HermesGateway()
    callbacksRef.current.onGatewayReady(gateway)
    setGateway(gateway)

    let bootCompleted = false
    let reconnectTimer: number | null = null
    let reconnectAttempts = 0
    let reconnectInFlight = false
    const MAX_RECONNECT_ATTEMPTS = 8
    const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000]

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    const attemptReconnect = async () => {
      if (cancelled || !bootCompleted || reconnectInFlight || gateway.connectionState === 'open') {
        return
      }

      reconnectInFlight = true
      clearReconnectTimer()

      try {
        const conn = await desktop.getConnection()

        if (cancelled) {
          return
        }

        publish(conn)
        await gateway.connect(conn.wsUrl)

        if (!cancelled) {
          reconnectAttempts = 0
        }
      } catch {
        if (!cancelled && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          const delay = BACKOFF_MS[Math.min(reconnectAttempts, BACKOFF_MS.length - 1)]
          reconnectAttempts += 1
          reconnectTimer = window.setTimeout(() => void attemptReconnect(), delay)
        }
      } finally {
        reconnectInFlight = false
      }
    }

    const scheduleReconnect = () => {
      if (cancelled || !bootCompleted || reconnectInFlight || reconnectTimer !== null) {
        return
      }

      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        return
      }

      const delay = BACKOFF_MS[Math.min(reconnectAttempts, BACKOFF_MS.length - 1)]
      reconnectAttempts += 1
      reconnectTimer = window.setTimeout(() => void attemptReconnect(), delay)
    }

    const offState = gateway.onState(st => {
      void setGatewayState(st)

      if (st === 'open') {
        reconnectAttempts = 0
        clearReconnectTimer()
      } else if (bootCompleted && (st === 'closed' || st === 'error')) {
        scheduleReconnect()
      }
    })
    const offEvent = gateway.onEvent(event => callbacksRef.current.handleGatewayEvent(event))

    const pingInterval = window.setInterval(() => {
      if (cancelled || gateway.connectionState !== 'open') {
        return
      }

      void gateway.request('ping').catch(() => undefined)
    }, 25_000)

    const onOnlineOrVisible = () => {
      if (IS_WEB && document.visibilityState === 'hidden') {
        return
      }

      if (bootCompleted && gateway.connectionState !== 'open') {
        reconnectAttempts = 0
        void attemptReconnect()
      }
    }

    const onManualRetry = () => {
      if (gateway.connectionState !== 'open') {
        bootCompleted = true
        reconnectAttempts = 0
        void attemptReconnect()
      }
    }

    window.addEventListener('online', onOnlineOrVisible)
    document.addEventListener('visibilitychange', onOnlineOrVisible)
    window.addEventListener('hermes:gateway-retry', onManualRetry)

    const offWindowState = desktop.onWindowStateChanged?.(payload => {
      const current = $connection.get()

      if (current) {
        publish({ ...current, ...payload })
      }
    })

    const offExit = desktop.onBackendExit(() => {
      if ($desktopBoot.get().running || $desktopBoot.get().visible) {
        failDesktopBoot('TchuekaM background process exited during startup.')
      }

      notify({
        kind: 'error',
        title: 'Backend stopped',
        message: 'TchuekaM background process exited.',
        durationMs: 0
      })
    })

    async function boot() {
      try {
        const conn = await desktop.getConnection()

        if (cancelled) {
          return
        }

        setDesktopBootStep({
          phase: 'renderer.gateway.connect',
          message: 'Connecting live desktop gateway',
          progress: 95
        })
        publish(conn)
        await gateway.connect(conn.wsUrl)

        if (cancelled) {
          return
        }

        setDesktopBootStep({
          phase: 'renderer.config',
          message: 'Loading TchuekaM settings',
          progress: 97
        })
        await callbacksRef.current.refreshHermesConfig()

        if (cancelled) {
          return
        }

        setDesktopBootStep({
          phase: 'renderer.sessions',
          message: 'Loading recent sessions',
          progress: 99
        })
        await callbacksRef.current.refreshSessions()
        bootCompleted = true
        completeDesktopBoot()
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err)
          failDesktopBoot(message)
          notifyError(err, 'Desktop boot failed')
          setSessionsLoading(false)
        }
      }
    }

    void boot()

    return () => {
      cancelled = true
      clearReconnectTimer()
      window.clearInterval(pingInterval)
      window.removeEventListener('online', onOnlineOrVisible)
      document.removeEventListener('visibilitychange', onOnlineOrVisible)
      window.removeEventListener('hermes:gateway-retry', onManualRetry)
      offState()
      offEvent()
      offExit()
      offWindowState?.()
      offBootProgress()
      gateway.close()
      publish(null)
      callbacksRef.current.onGatewayReady(null)
      setGateway(null)
    }
  }, [])
}
