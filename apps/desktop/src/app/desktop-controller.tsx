import { useStore } from '@nanostores/react'
import { useQueryClient } from '@tanstack/react-query'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'

import { BootFailureOverlay } from '@/components/boot-failure-overlay'
import { DesktopInstallOverlay } from '@/components/desktop-install-overlay'
import { GatewayConnectingOverlay } from '@/components/gateway-connecting-overlay'
import { Pane, PaneMain } from '@/components/pane-shell'
import { Codicon } from '@/components/ui/codicon'
import { useIsCompactViewport } from '@/hooks/use-mobile'
import { HAS_NATIVE_FS, IS_DESKTOP, IS_LOCKED_DEMO } from '@/lib/platform'
import { CHAT_SIDEBAR_PANE_ID } from '@/store/layout'
import { setPaneOpen } from '@/store/panes'
import { useSkinCommand } from '@/themes/use-skin-command'

import { formatRefValue } from '../components/assistant-ui/directive-text'
import { getSessionMessages, listSessions } from '../hermes'
import { preserveLocalAssistantErrors, toChatMessages } from '../lib/chat-messages'
import { $pinnedSessionIds, $sessionsLimit, bumpSessionsLimit, FILE_BROWSER_DEFAULT_WIDTH, FILE_BROWSER_MAX_WIDTH, FILE_BROWSER_MIN_WIDTH, pinSession, SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH, unpinSession } from '../store/layout'
import { initIntelligenceListeners } from '../store/intelligence'
import { $filePreviewTarget, $previewTarget, closeActiveRightRailTab } from '../store/preview'
import {
  $activeSessionId,
  $currentCwd,
  $freshDraftReady,
  $gatewayState,
  $selectedStoredSessionId,
  $sessions,
  $workingSessionIds,
  mergeWorkingSessions,
  sessionPinId,
  setAwaitingResponse,
  setBusy,
  setCurrentBranch,
  setCurrentCwd,
  setCurrentModel,
  setCurrentProvider,
  setMessages,
  setSessions,
  setSessionsLoading,
  setSessionsTotal
} from '../store/session'
import { openUpdatesWindow, startUpdatePoller, stopUpdatePoller } from '../store/updates'

import { ChatView } from './chat'
import { useComposerActions } from './chat/hooks/use-composer-actions'
import {
  ChatPreviewRail,
  PREVIEW_RAIL_MAX_WIDTH,
  PREVIEW_RAIL_MIN_WIDTH,
  PREVIEW_RAIL_PANE_WIDTH
} from './chat/right-rail'
import { ChatSidebar } from './chat/sidebar'
import { useGatewayBoot } from './gateway/hooks/use-gateway-boot'
import { useGatewayRequest } from './gateway/hooks/use-gateway-request'
import { MobilePromoBanner } from './mobile/mobile-banner'
import { ModelPickerOverlay } from './model-picker-overlay'
import { ModelVisibilityOverlay } from './model-visibility-overlay'
import { RightSidebarPane } from './right-sidebar'
import { $terminalTakeover } from './right-sidebar/store'
import { PersistentTerminal, TerminalSlot } from './right-sidebar/terminal/persistent'
import { NEW_CHAT_ROUTE, routeSessionId, sessionRoute, SETTINGS_ROUTE } from './routes'
import { useContextSuggestions } from './session/hooks/use-context-suggestions'
import { useCwdActions } from './session/hooks/use-cwd-actions'
import { useHermesConfig } from './session/hooks/use-hermes-config'
import { useMessageStream } from './session/hooks/use-message-stream'
import { useModelControls } from './session/hooks/use-model-controls'
import { usePreviewRouting } from './session/hooks/use-preview-routing'
import { usePromptActions } from './session/hooks/use-prompt-actions'
import { useRouteResume } from './session/hooks/use-route-resume'
import { useSessionActions } from './session/hooks/use-session-actions'
import { useSessionStateCache } from './session/hooks/use-session-state-cache'
import { AppShell } from './shell/app-shell'
import { useOverlayRouting } from './shell/hooks/use-overlay-routing'
import { useStatusSnapshot } from './shell/hooks/use-status-snapshot'
import { useStatusbarItems } from './shell/hooks/use-statusbar-items'
import { ModelMenuPanel } from './shell/model-menu-panel'
import type { StatusbarItem } from './shell/statusbar-controls'
import type { TitlebarTool } from './shell/titlebar-controls'
import { useGroupRegistry } from './shell/use-group-registry'
import { UpdatesOverlay } from './updates-overlay'

const AgentsView = lazy(async () => ({ default: (await import('./agents')).AgentsView }))
const ArtifactsView = lazy(async () => ({ default: (await import('./artifacts')).ArtifactsView }))
const BusinessView = lazy(async () => ({ default: (await import('./business')).BusinessView }))
const ImageStudioView = lazy(async () => ({ default: (await import('./image-studio')).ImageStudioView }))
const CommandCenterView = lazy(async () => ({ default: (await import('./command-center')).CommandCenterView }))
const CronView = lazy(async () => ({ default: (await import('./cron')).CronView }))
const MessagingView = lazy(async () => ({ default: (await import('./messaging')).MessagingView }))
const MobileView = lazy(async () => ({ default: (await import('./mobile')).MobileView }))
const ProfilesView = lazy(async () => ({ default: (await import('./profiles')).ProfilesView }))
const SettingsView = lazy(async () => ({ default: (await import('./settings')).SettingsView }))
const SkillsView = lazy(async () => ({ default: (await import('./skills')).SkillsView }))

export function DesktopController() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const isCompact = useIsCompactViewport()

  useEffect(() => {
    if (isCompact) {
      setPaneOpen(CHAT_SIDEBAR_PANE_ID, false)
    }
  }, [isCompact, location.pathname])
  const navigate = useNavigate()

  const busyRef = useRef(false)
  const creatingSessionRef = useRef(false)
  const refreshSessionsRequestRef = useRef(0)

  const gatewayState = useStore($gatewayState)
  const activeSessionId = useStore($activeSessionId)
  const currentCwd = useStore($currentCwd)
  const freshDraftReady = useStore($freshDraftReady)
  const filePreviewTarget = useStore($filePreviewTarget)
  const previewTarget = useStore($previewTarget)
  const selectedStoredSessionId = useStore($selectedStoredSessionId)
  const terminalTakeover = useStore($terminalTakeover)

  const routedSessionId = routeSessionId(location.pathname)
  const routeToken = `${location.pathname}:${location.search}:${location.hash}`
  const routeTokenRef = useRef(routeToken)
  routeTokenRef.current = routeToken
  const getRouteToken = useCallback(() => routeTokenRef.current, [])

  const {
    agentsOpen,
    chatOpen,
    closeOverlayToPreviousRoute,
    commandCenterInitialSection,
    commandCenterOpen,
    currentView,
    openAgents,
    openCommandCenterSection,
    settingsOpen,
    toggleCommandCenter
  } = useOverlayRouting()

  const terminalTakeoverActive = chatOpen && terminalTakeover

  const titlebarToolGroups = useGroupRegistry<TitlebarTool>()
  const statusbarItemGroups = useGroupRegistry<StatusbarItem>()
  const setTitlebarToolGroup = titlebarToolGroups.set
  const setStatusbarItemGroup = statusbarItemGroups.set

  const {
    activeSessionIdRef,
    ensureSessionState,
    runtimeIdByStoredSessionIdRef,
    selectedStoredSessionIdRef,
    sessionStateByRuntimeIdRef,
    syncSessionStateToView,
    updateSessionState
  } = useSessionStateCache({
    activeSessionId,
    busyRef,
    selectedStoredSessionId,
    setAwaitingResponse,
    setBusy,
    setMessages
  })

  const { connectionRef, gatewayRef, requestGateway } = useGatewayRequest()

  useEffect(() => {
    window.hermesDesktop?.setPreviewShortcutActive?.(Boolean(chatOpen && (filePreviewTarget || previewTarget)))
  }, [chatOpen, filePreviewTarget, previewTarget])

  useEffect(() => {
    startUpdatePoller()
    const stopIntelligence = initIntelligenceListeners()
    const unsubscribe = window.hermesDesktop?.onOpenUpdatesRequested?.(() => openUpdatesWindow())

    return () => {
      unsubscribe?.()
      stopIntelligence()
      stopUpdatePoller()
    }
  }, [])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!$filePreviewTarget.get() && !$previewTarget.get()) {
        return
      }

      if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'w') {
        event.preventDefault()
        event.stopPropagation()
        closeActiveRightRailTab()
      }
    }

    const unsubscribe = window.hermesDesktop?.onClosePreviewRequested?.(closeActiveRightRailTab)

    window.addEventListener('keydown', onKeyDown, { capture: true })

    return () => {
      unsubscribe?.()
      window.removeEventListener('keydown', onKeyDown, { capture: true })
    }
  }, [])

  const refreshSessions = useCallback(async () => {
    const requestId = refreshSessionsRequestRef.current + 1
    refreshSessionsRequestRef.current = requestId
    setSessionsLoading(true)

    try {
      const limit = $sessionsLimit.get()
      // Require at least one message so abandoned/empty "Untitled" drafts (one
      // was created per TUI/desktop launch before the lazy-create fix) don't
      // clutter the sidebar.
      const result = await listSessions(limit, 1)

      if (refreshSessionsRequestRef.current === requestId) {
        // Don't hard-replace: a session whose first turn is still in flight has
        // message_count 0 in the DB, so min_messages=1 omits it. Since every
        // message.complete refreshes the list, a plain replace would drop the
        // other still-running new chats the moment one of them finishes. Keep
        // any working session the server hasn't surfaced yet.
        setSessions(prev => mergeWorkingSessions(prev, result.sessions, $workingSessionIds.get()))
        setSessionsTotal(typeof result.total === 'number' ? result.total : result.sessions.length)
      }
    } finally {
      if (refreshSessionsRequestRef.current === requestId) {
        setSessionsLoading(false)
      }
    }
  }, [])

  const loadMoreSessions = useCallback(() => {
    bumpSessionsLimit()
    void refreshSessions()
  }, [refreshSessions])

  const toggleSelectedPin = useCallback(() => {
    const sessionId = $selectedStoredSessionId.get()

    if (!sessionId) {
      return
    }

    // Pin on the durable lineage-root id so the pin survives auto-compression.
    const session = $sessions.get().find(s => s.id === sessionId || s._lineage_root_id === sessionId)
    const pinId = session ? sessionPinId(session) : sessionId

    if ($pinnedSessionIds.get().includes(pinId)) {
      unpinSession(pinId)
    } else {
      pinSession(pinId)
    }
  }, [])

  const { gatewayLogLines, inferenceStatus, statusSnapshot } = useStatusSnapshot(gatewayState, requestGateway)

  const updateActiveSessionRuntimeInfo = useCallback(
    (info: { branch?: string; cwd?: string }) => {
      const sessionId = activeSessionIdRef.current

      if (!sessionId) {
        return
      }

      updateSessionState(sessionId, state => ({
        ...state,
        branch: info.branch ?? state.branch,
        cwd: info.cwd ?? state.cwd
      }))
    },
    [activeSessionIdRef, updateSessionState]
  )

  const { changeSessionCwd, refreshProjectBranch } = useCwdActions({
    activeSessionId,
    activeSessionIdRef,
    onSessionRuntimeInfo: updateActiveSessionRuntimeInfo,
    requestGateway
  })

  const { refreshHermesConfig, sttEnabled, voiceMaxRecordingSeconds } = useHermesConfig({
    activeSessionIdRef,
    refreshProjectBranch
  })

  const { refreshCurrentModel, selectModel, updateModelOptionsCache } = useModelControls({
    activeSessionId,
    queryClient,
    requestGateway
  })

  const openProviderSettings = useCallback(() => {
    navigate(`${SETTINGS_ROUTE}?tab=keys`)
  }, [navigate])

  const modelMenuContent = useMemo(
    () =>
      gatewayState === 'open' ? (
        <ModelMenuPanel
          gateway={gatewayRef.current || undefined}
          onSelectModel={selectModel}
          requestGateway={requestGateway}
        />
      ) : null,
    [gatewayRef, gatewayState, requestGateway, selectModel]
  )

  useContextSuggestions({
    activeSessionId,
    activeSessionIdRef,
    currentCwd,
    gatewayState,
    requestGateway
  })

  const hydrateFromStoredSession = useCallback(
    async (
      attempts = 1,
      storedSessionId = selectedStoredSessionIdRef.current,
      runtimeSessionId = activeSessionIdRef.current
    ) => {
      if (!storedSessionId || !runtimeSessionId) {
        return
      }

      for (let index = 0; index < Math.max(1, attempts); index += 1) {
        try {
          const latest = await getSessionMessages(storedSessionId)
          updateSessionState(
            runtimeSessionId,
            state => ({
              ...state,
              messages: preserveLocalAssistantErrors(toChatMessages(latest.messages), state.messages)
            }),
            storedSessionId
          )

          return
        } catch {
          // Best-effort fallback when live stream payloads are empty.
        }

        if (index < attempts - 1) {
          await new Promise(resolve => window.setTimeout(resolve, 250))
        }
      }
    },
    [activeSessionIdRef, selectedStoredSessionIdRef, updateSessionState]
  )

  const { handleGatewayEvent } = useMessageStream({
    activeSessionIdRef,
    hydrateFromStoredSession,
    queryClient,
    refreshHermesConfig,
    refreshSessions,
    updateSessionState
  })

  const { handleDesktopGatewayEvent, restartPreviewServer } = usePreviewRouting({
    activeSessionIdRef,
    baseHandleGatewayEvent: handleGatewayEvent,
    currentCwd,
    currentView,
    requestGateway,
    routedSessionId,
    selectedStoredSessionId
  })

  const {
    archiveSession,
    branchCurrentSession,
    createBackendSessionForSend,
    openSettings,
    removeSession,
    resumeSession,
    selectSidebarItem,
    startFreshSessionDraft
  } = useSessionActions({
    activeSessionId,
    activeSessionIdRef,
    busyRef,
    creatingSessionRef,
    ensureSessionState,
    getRouteToken,
    navigate,
    requestGateway,
    runtimeIdByStoredSessionIdRef,
    selectedStoredSessionId,
    selectedStoredSessionIdRef,
    sessionStateByRuntimeIdRef,
    syncSessionStateToView,
    updateSessionState
  })

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null

      const editing =
        target?.isContentEditable ||
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement

      if (event.defaultPrevented || event.repeat || event.altKey || event.code !== 'KeyN') {
        return
      }

