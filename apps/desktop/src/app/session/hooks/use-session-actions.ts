import type { MutableRefObject } from 'react'
import { useCallback, useRef } from 'react'
import type { NavigateFunction } from 'react-router-dom'

import { deleteSession, getSessionMessages, setSessionArchived } from '@/hermes'
import { type ChatMessage, chatMessageText, preserveLocalAssistantErrors, toChatMessages } from '@/lib/chat-messages'
import { IS_DESKTOP, IS_LOCKED_DEMO } from '@/lib/platform'
import { normalizePersonalityValue } from '@/lib/chat-runtime'
import { embeddedImageUrls, textWithoutEmbeddedImages } from '@/lib/embedded-images'
import { clearComposerAttachments, clearComposerDraft } from '@/store/composer'
import { clearQueuedPrompts } from '@/store/composer-queue'
import { $pinnedSessionIds } from '@/store/layout'
import { clearNotifications, notify, notifyError } from '@/store/notifications'
import { requestDesktopOnboarding } from '@/store/onboarding'
import {
  $currentCwd,
  $currentModel,
  $currentProvider,
  $messages,
  $sessions,
  getRememberedWorkspaceCwd,
  setActiveSessionId,
  setAwaitingResponse,
  setBusy,
  setCurrentBranch,
  setCurrentCwd,
  setCurrentFastMode,
  setCurrentModel,
  setCurrentPersonality,
  setCurrentProvider,
  setCurrentReasoningEffort,
  setCurrentServiceTier,
  setCurrentUsage,
  setFreshDraftReady,
  setIntroSeed,
  setMessages,
  setSelectedStoredSessionId,
  setSessions,
  setSessionStartedAt,
  setSessionsTotal,
  setTurnStartedAt
} from '@/store/session'
import { reportBackendContract } from '@/store/updates'
import type { SessionCreateResponse, SessionInfo, SessionResumeResponse, UsageStats } from '@/types/hermes'

import { NEW_CHAT_ROUTE, sessionRoute, SETTINGS_ROUTE } from '../../routes'
import type { ClientSessionState, SidebarNavItem } from '../../types'

interface SessionActionsOptions {
  activeSessionId: string | null
  activeSessionIdRef: MutableRefObject<string | null>
  busyRef: MutableRefObject<boolean>
  creatingSessionRef: MutableRefObject<boolean>
  ensureSessionState: (sessionId: string, storedSessionId?: string | null) => ClientSessionState
  getRouteToken: () => string
  navigate: NavigateFunction
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
  runtimeIdByStoredSessionIdRef: MutableRefObject<Map<string, string>>
  selectedStoredSessionId: string | null
  selectedStoredSessionIdRef: MutableRefObject<string | null>
  sessionStateByRuntimeIdRef: MutableRefObject<Map<string, ClientSessionState>>
  syncSessionStateToView: (sessionId: string, state: ClientSessionState) => void
  updateSessionState: (
    sessionId: string,
    updater: (state: ClientSessionState) => ClientSessionState,
    storedSessionId?: string | null
  ) => ClientSessionState
}

function withAppendedText(message: ChatMessage, suffix: string): ChatMessage {
  let appended = false

  const parts = message.parts.map(part => {
    if (part.type !== 'text' || appended) {
      return part
    }

    appended = true

    return { ...part, text: `${part.text}${suffix}` }
  })

  return appended ? { ...message, parts } : message
}

function preserveReasoningParts(message: ChatMessage, previous: ChatMessage): ChatMessage {
  if (message.parts.some(part => part.type === 'reasoning')) {
    return message
  }

  const reasoningParts = previous.parts.filter(part => part.type === 'reasoning')

  return reasoningParts.length ? { ...message, parts: [...reasoningParts, ...message.parts] } : message
}

function chatMessagesEquivalent(a: ChatMessage, b: ChatMessage): boolean {
  if (
    a.id !== b.id ||
    a.role !== b.role ||
    a.pending !== b.pending ||
    a.error !== b.error ||
    a.hidden !== b.hidden ||
    a.branchGroupId !== b.branchGroupId
  ) {
    return false
  }

  if (a.parts.length !== b.parts.length) {
    return false
  }

  return a.parts.every((part, index) => JSON.stringify(part) === JSON.stringify(b.parts[index]))
}

function chatMessageArraysEquivalent(a: ChatMessage[], b: ChatMessage[]): boolean {
  return a.length === b.length && a.every((message, index) => chatMessagesEquivalent(message, b[index]))
}

function reconcileResumeMessages(nextMessages: ChatMessage[], previousMessages: ChatMessage[]): ChatMessage[] {
  if (!previousMessages.length) {
    return nextMessages
  }

  const previousByRoleOrdinal = new Map<string, ChatMessage>()
  const previousRoleCounts = new Map<string, number>()

  for (const message of previousMessages) {
    const ordinal = previousRoleCounts.get(message.role) ?? 0
    previousRoleCounts.set(message.role, ordinal + 1)
    previousByRoleOrdinal.set(`${message.role}:${ordinal}`, message)
  }

  const nextRoleCounts = new Map<string, number>()

  return nextMessages.map(message => {
    const ordinal = nextRoleCounts.get(message.role) ?? 0
    nextRoleCounts.set(message.role, ordinal + 1)

    const previous = previousByRoleOrdinal.get(`${message.role}:${ordinal}`)

    if (!previous) {
      return message
    }

    const nextText = chatMessageText(message).trim()
    const previousText = chatMessageText(previous)
    const previousVisibleText = textWithoutEmbeddedImages(previousText)
    let preserved = message

    if (nextText === previousVisibleText || nextText === previousText.trim()) {
      preserved = preserveReasoningParts(preserved, previous)
    }

    const previousImages = embeddedImageUrls(previousText)

    if (!previousImages.length || embeddedImageUrls(chatMessageText(preserved)).length) {
      return preserved
    }

    if (nextText !== previousVisibleText) {
      return preserved
    }

    return withAppendedText(preserved, previousImages.map(url => `\n${url}`).join(''))
  })
}

function upsertOptimisticSession(
  created: SessionCreateResponse,
  id: string,
  title: string | null = null,
  preview: string | null = null
) {
  const now = Date.now() / 1000

  const session: SessionInfo = {
    cwd: created.info?.cwd ?? null,
    ended_at: null,
    id,
    input_tokens: 0,
    is_active: true,
    last_active: now,
    message_count: created.message_count ?? created.messages?.length ?? 0,
    model: created.info?.model ?? null,
    output_tokens: 0,
    preview,
    source: 'tui',
    started_at: now,
    title,
    tool_call_count: 0
  }

  setSessions(prev => [session, ...prev.filter(s => s.id !== id)])
}

function patchSessionWorkspace(sessionId: string, cwd: string | undefined) {
  if (!cwd) {
    return
  }

  setSessions(prev => prev.map(session => (session.id === sessionId ? { ...session, cwd } : session)))
}

function applyRuntimeInfo(
  info: SessionCreateResponse['info'] | undefined
): Partial<Pick<ClientSessionState, 'branch' | 'cwd'>> | null {
  if (!info) {
    return null
  }

  const sessionState: Partial<Pick<ClientSessionState, 'branch' | 'cwd'>> = {}

  reportBackendContract(info.desktop_contract)

  if (info.credential_warning) {
    requestDesktopOnboarding(info.credential_warning)
  }

  if (info.model) {
    setCurrentModel(info.model)
  }

  if (info.provider) {
    setCurrentProvider(info.provider)
  }

  if (info.cwd) {
    setCurrentCwd(info.cwd)
    sessionState.cwd = info.cwd
  }

  if (info.branch !== undefined) {
    setCurrentBranch(info.branch || '')
    sessionState.branch = info.branch || ''
  }

  if (typeof info.personality === 'string') {
    setCurrentPersonality(normalizePersonalityValue(info.personality))
  }

  if (typeof info.reasoning_effort === 'string') {
    setCurrentReasoningEffort(info.reasoning_effort)
  }

  if (typeof info.service_tier === 'string') {
    setCurrentServiceTier(info.service_tier)
  }

  if (typeof info.fast === 'boolean') {
    setCurrentFastMode(info.fast)
  }

  if (info.usage) {
    setCurrentUsage(current => ({ ...current, ...info.usage }))
  }

  return sessionState
}

export function useSessionActions({
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
}: SessionActionsOptions) {
  const resumeRequestRef = useRef(0)

  const startFreshSessionDraft = useCallback(
    (replaceRoute = false) => {
      busyRef.current = false
      setBusy(false)
      setAwaitingResponse(false)
      clearNotifications()
      setIntroSeed(seed => seed + 1)
      navigate(NEW_CHAT_ROUTE, { replace: replaceRoute })
      setActiveSessionId(null)
      activeSessionIdRef.current = null
      setSelectedStoredSessionId(null)
      selectedStoredSessionIdRef.current = null
      setMessages([])
      setCurrentUsage({
        calls: 0,
        input: 0,
        output: 0,
        total: 0
      })
      setSessionStartedAt(null)
      setTurnStartedAt(null)
      // New chats inherit the current workspace.
      setCurrentCwd(getRememberedWorkspaceCwd())
      setCurrentBranch('')
      clearComposerDraft()
      clearComposerAttachments()
      setFreshDraftReady(true)
    },
    [activeSessionIdRef, busyRef, navigate, selectedStoredSessionIdRef]
  )

  const createBackendSessionForSend = useCallback(async (preview: string | null = null): Promise<string | null> => {
    const startingActiveSessionId = activeSessionIdRef.current
    const startingStoredSessionId = selectedStoredSessionIdRef.current
    const startingRouteToken = getRouteToken()

    creatingSessionRef.current = true

    try {
      const cwd = $currentCwd.get().trim() || getRememberedWorkspaceCwd()
      const created = await requestGateway<SessionCreateResponse>('session.create', { cols: 96, ...(cwd && { cwd }) })
      const stored = created.stored_session_id ?? null

      if (
        activeSessionIdRef.current !== startingActiveSessionId ||
        selectedStoredSessionIdRef.current !== startingStoredSessionId ||
        getRouteToken() !== startingRouteToken
      ) {
        await requestGateway('session.close', { session_id: created.session_id }).catch(() => undefined)

        return null
      }

      activeSessionIdRef.current = created.session_id
      selectedStoredSessionIdRef.current = stored
      ensureSessionState(created.session_id, stored)

      if (stored) {
        // Seed the sidebar preview with the user's first message so the row
        // reads meaningfully while the turn is in flight, instead of flashing
        // "Untitled session" until the turn persists and auto-title runs. The
        // server later returns its own preview/title and supersedes this.
        upsertOptimisticSession(created, stored, null, preview?.trim() || null)
        navigate(sessionRoute(stored), { replace: true })
      }

      const chosenModel = $currentModel.get().trim()
      const chosenProvider = $currentProvider.get().trim()

      setFreshDraftReady(false)
      setActiveSessionId(created.session_id)
      setSelectedStoredSessionId(stored)
      setSessionStartedAt(Date.now())
      const runtimeInfo = applyRuntimeInfo(created.info)

      if (
        IS_LOCKED_DEMO &&
        chosenModel &&
        chosenProvider &&
        (created.info?.model !== chosenModel || created.info?.provider !== chosenProvider)
      ) {
        await requestGateway('model.switch', {
          session_id: created.session_id,
          provider: chosenProvider,
          model: chosenModel
        }).catch(() => undefined)
        setCurrentModel(chosenModel)
        setCurrentProvider(chosenProvider)
      }

      if (runtimeInfo) {
        updateSessionState(created.session_id, state => ({ ...state, ...runtimeInfo }), stored)
      }

      return created.session_id
    } finally {
      window.setTimeout(() => {
        creatingSessionRef.current = false
      }, 0)
    }
  }, [
    activeSessionIdRef,
    creatingSessionRef,
    ensureSessionState,
    getRouteToken,
    navigate,
    requestGateway,
    selectedStoredSessionIdRef,
    updateSessionState
  ])

  const selectSidebarItem = useCallback(
    (item: SidebarNavItem) => {
      if (item.action === 'new-session') {
        startFreshSessionDraft()

        return
      }

      if (item.id === 'image-studio') {
        if (IS_DESKTOP && window.hermesDesktop?.openImageStudioWindow) {
          void window.hermesDesktop.openImageStudioWindow()

          return
        }
      }

      if (item.route) {
        navigate(item.route)
      }
    },
    [navigate, startFreshSessionDraft]
  )

  const openSettings = useCallback(() => {
    navigate(SETTINGS_ROUTE)
  }, [navigate])

  const closeSettings = useCallback(() => {
    if (selectedStoredSessionId) {
      navigate(sessionRoute(selectedStoredSessionId))

      return
    }

