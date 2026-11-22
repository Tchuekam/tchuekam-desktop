import { useStore } from '@nanostores/react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'

import type { SetTitlebarToolGroup, TitlebarTool } from '@/app/shell/titlebar-controls'
import { Bug } from '@/lib/icons'
import { IS_DESKTOP } from '@/lib/platform'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'
import { $previewServerRestart, failPreviewServerRestart, type PreviewTarget } from '@/store/preview'

import {
  clampConsoleHeight,
  compactUrl,
  formatLogLine,
  isNearConsoleBottom,
  PreviewConsolePanel,
  PreviewConsoleTitlebarIcon
} from './preview-console'
import { type ConsoleEntry, createPreviewConsoleState } from './preview-console-state'
import { LocalFilePreview, PreviewEmptyState } from './preview-file'

type PreviewWebview = HTMLElement & {
  closeDevTools?: () => void
  getURL?: () => string
  isDevToolsOpened?: () => boolean
  openDevTools?: () => void
  reload?: () => void
  reloadIgnoringCache?: () => void
}

interface PreviewPaneProps {
  embedded?: boolean
  onRestartServer?: (url: string, context?: string) => Promise<string>
  reloadRequest?: number
  setTitlebarToolGroup?: SetTitlebarToolGroup
  target: PreviewTarget
}

interface PreviewLoadErrorState {
  code?: number
  description: string
  url: string
}

const FILE_RELOAD_DEBOUNCE_MS = 200
const SERVER_RESTART_TIMEOUT_MS = 45_000

function loadErrorTitle(error: PreviewLoadErrorState): string {
  const description = error.description.toLowerCase()

  if (description.includes('module script') || description.includes('mime type')) {
    return 'Preview app failed to boot'
  }

  if (description.includes('connection') || description.includes('refused') || description.includes('not found')) {
    return 'Server not found'
  }

  return 'Preview failed to load'
}

function isModuleMimeError(message: string): boolean {
  const lower = message.toLowerCase()

  return lower.includes('failed to load module script') && lower.includes('mime type')
}

function PreviewLoadError({
  consoleHeight = 0,
  error,
  onRestartServer,
  onRetry,
  restarting
}: {
  consoleHeight?: number
  error: PreviewLoadErrorState
  onRestartServer?: () => void
  onRetry: () => void
  restarting?: boolean
}) {
  return (
    <PreviewEmptyState
      body={
        <>
          <a
            className="pointer-events-auto block cursor-pointer font-mono text-muted-foreground/90 underline decoration-current/20 underline-offset-4 transition-colors hover:text-foreground"
            href={error.url}
            onClick={event => {
              event.preventDefault()
              void window.hermesDesktop?.openExternal(error.url)
            }}
          >
            {compactUrl(error.url)}
            {error.code ? ` (${error.code})` : ''}
          </a>
          <div className="mt-1 text-[0.6875rem] text-muted-foreground/70">{error.description}</div>
        </>
      }
      consoleHeight={consoleHeight}
      primaryAction={{ label: 'Try again', onClick: onRetry }}
      secondaryAction={
        onRestartServer
          ? {
              disabled: restarting,
              label: restarting ? 'TchuekaM is restarting...' : 'Ask TchuekaM to restart the server',
              onClick: onRestartServer
            }
          : undefined
      }
      title={loadErrorTitle(error)}
    />
  )
}

const TITLEBAR_GROUP_ID = 'preview'

export function PreviewPane({
  embedded = false,
  onRestartServer,
  reloadRequest = 0,
  setTitlebarToolGroup,
  target
}: PreviewPaneProps) {
  const [consoleState] = useState(() => createPreviewConsoleState())
  const consoleBodyRef = useRef<HTMLDivElement | null>(null)
  const consoleShouldStickRef = useRef(true)
  const hostRef = useRef<HTMLDivElement | null>(null)
  const lastReloadRequestRef = useRef(reloadRequest)
  const lastRestartEventRef = useRef('')
  const previewContentRef = useRef<HTMLDivElement | null>(null)
  const webviewRef = useRef<PreviewWebview | null>(null)
  const previewServerRestart = useStore($previewServerRestart)
  const consoleHeight = useStore(consoleState.$height)
  const consoleOpen = useStore(consoleState.$open)
  const [currentUrl, setCurrentUrl] = useState(target.url)
  const [devtoolsOpen, setDevtoolsOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<PreviewLoadErrorState | null>(null)
  const [localReloadKey, setLocalReloadKey] = useState(0)
  const isWebPreview = target.kind === 'url' || (target.previewKind === 'html' && target.renderMode !== 'source')
  const currentLabel = compactUrl(currentUrl)

  const previewLabel =
    target.label && target.label.replace(/\/$/, '') !== currentLabel.replace(/\/$/, '') ? target.label : currentLabel

  const restartingServer =
    previewServerRestart?.status === 'running' &&
    (previewServerRestart.url === target.url || previewServerRestart.url === currentUrl)

  const startConsoleResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault()

      const handle = event.currentTarget
      const pointerId = event.pointerId
      const startY = event.clientY
      const startHeight = consoleHeight
      const previousCursor = document.body.style.cursor
      const previousUserSelect = document.body.style.userSelect
      let active = true

      handle.setPointerCapture?.(pointerId)

      document.body.style.cursor = 'row-resize'
      document.body.style.userSelect = 'none'

      const handleMove = (moveEvent: PointerEvent) => {
        if (!active) {
          return
        }

        consoleState.setHeight(clampConsoleHeight(startHeight + startY - moveEvent.clientY))
      }

      const cleanup = () => {
        if (!active) {
          return
        }

        active = false
        document.body.style.cursor = previousCursor
        document.body.style.userSelect = previousUserSelect
        handle.releasePointerCapture?.(pointerId)
        window.removeEventListener('pointermove', handleMove, true)
        window.removeEventListener('pointerup', cleanup, true)
        window.removeEventListener('pointercancel', cleanup, true)
        window.removeEventListener('blur', cleanup)
        handle.removeEventListener('lostpointercapture', cleanup)
      }

      window.addEventListener('pointermove', handleMove, true)
      window.addEventListener('pointerup', cleanup, true)
      window.addEventListener('pointercancel', cleanup, true)
      window.addEventListener('blur', cleanup)
      handle.addEventListener('lostpointercapture', cleanup)
    },
    [consoleHeight, consoleState]
  )

  const reloadPreview = useCallback(() => {
    setLoadError(null)

    if (!isWebPreview) {
      setLocalReloadKey(key => key + 1)

      return
    }

    if (webviewRef.current?.reloadIgnoringCache) {
      webviewRef.current.reloadIgnoringCache()
    } else {
      webviewRef.current?.reload?.()
    }
  }, [isWebPreview])

  const appendConsoleEntry = useCallback(
    (entry: Omit<ConsoleEntry, 'id'>) => {
      consoleShouldStickRef.current = isNearConsoleBottom(consoleBodyRef.current)
      consoleState.append(entry)
    },
    [consoleState]
  )

  const restartServer = useCallback(async () => {
    if (!onRestartServer) {
      return
    }

    // Auto-open the preview console so the user can see progress events
    // streaming back from the background agent. Without this, clicking
    // "Ask Hermes to restart the server" looked like it did nothing —
    // the work was happening, but in a collapsed pane.
    consoleState.setOpen(true)

    try {
      const context = consoleState.$logs.get().slice(-12).map(formatLogLine).join('\n')
      const taskId = await onRestartServer(currentUrl, context || undefined)

      appendConsoleEntry({
        level: 1,
        message: `TchuekaM is looking for a preview server to restart (${taskId})`
      })

      notify({
        kind: 'info',
        title: 'Restarting preview server',
        message: 'TchuekaM is working in the background. Watch the preview console for progress.',
        durationMs: 4000
      })
    } catch (error) {
      appendConsoleEntry({
        level: 2,
        message: `Could not start server restart: ${error instanceof Error ? error.message : String(error)}`
      })
      notifyError(error, 'Server restart failed')
    }
  }, [appendConsoleEntry, consoleState, currentUrl, onRestartServer])

  const toggleDevTools = useCallback(() => {
    const webview = webviewRef.current

    if (!webview?.openDevTools) {
      return
    }

    if (webview.isDevToolsOpened?.()) {
      webview.closeDevTools?.()
      setDevtoolsOpen(false)

      return
    }

    webview.openDevTools()
    setDevtoolsOpen(true)
  }, [])

  useEffect(() => {
    if (!setTitlebarToolGroup) {
      return
    }

    const tools: TitlebarTool[] = [
      ...(isWebPreview
        ? [
            {
              active: consoleOpen,
              icon: <PreviewConsoleTitlebarIcon consoleState={consoleState} />,
              id: `${TITLEBAR_GROUP_ID}-console`,
              label: consoleOpen ? 'Hide preview console' : 'Show preview console',
              onSelect: () => consoleState.setOpen(open => !open)
            },
            {
              active: devtoolsOpen,
              icon: <Bug />,
              id: `${TITLEBAR_GROUP_ID}-devtools`,
              label: devtoolsOpen ? 'Hide preview DevTools' : 'Open preview DevTools',
              onSelect: toggleDevTools
            }
          ]
        : [])
    ]

    setTitlebarToolGroup(TITLEBAR_GROUP_ID, tools)

    return () => setTitlebarToolGroup(TITLEBAR_GROUP_ID, [])
  }, [consoleOpen, consoleState, devtoolsOpen, isWebPreview, setTitlebarToolGroup, toggleDevTools])

  useEffect(() => {
    if (!consoleOpen) {
      return
    }

    consoleShouldStickRef.current = true

    const handle = window.requestAnimationFrame(() => {
      const consoleBody = consoleBodyRef.current
      consoleBody?.scrollTo({ top: consoleBody.scrollHeight })
    })

    return () => window.cancelAnimationFrame(handle)
  }, [consoleOpen])

  useEffect(() => {
    if (
      !previewServerRestart ||
      !previewServerRestart.message ||
      (previewServerRestart.url !== target.url && previewServerRestart.url !== currentUrl)
    ) {
      return
    }

    const eventKey = `${previewServerRestart.taskId}:${previewServerRestart.status}:${previewServerRestart.message || ''}`

    if (eventKey === lastRestartEventRef.current) {
      return
    }

    lastRestartEventRef.current = eventKey
    appendConsoleEntry({
      level: previewServerRestart.status === 'error' ? 2 : 1,
      message:
