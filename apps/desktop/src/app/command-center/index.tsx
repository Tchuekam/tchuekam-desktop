import { useStore } from '@nanostores/react'
import {
  IconBookmark,
  IconBookmarkFilled,
  IconDownload,
  IconRefresh,
  IconTrash
} from '@tabler/icons-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  getActionStatus,
  getLogs,
  getStatus,
  getUsageAnalytics,
  restartGateway,
  searchSessions,
  updateHermes
} from '@/hermes'
import type {
  ActionStatusResponse,
  AnalyticsResponse,
  SessionInfo,
  SessionSearchResult as SessionSearchApiResult,
  StatusResponse
} from '@/hermes'
import { sessionTitle } from '@/lib/chat-runtime'
import { Activity, AlertCircle, BarChart3, Pin } from '@/lib/icons'
import { IS_LOCKED_DEMO } from '@/lib/platform'
import { exportSession } from '@/lib/session-export'
import { cn } from '@/lib/utils'
import { upsertDesktopActionTask } from '@/store/activity'
import { $pinnedSessionIds, pinSession, unpinSession } from '@/store/layout'
import { $sessions } from '@/store/session'

import { useRouteEnumParam } from '../hooks/use-route-enum-param'
import { OverlayActionButton, OverlayCard, overlayCardClass, OverlayIconButton } from '../overlays/overlay-chrome'
import { OverlaySearchInput } from '../overlays/overlay-search-input'
import { OverlayMain, OverlayNavItem, OverlaySidebar, OverlaySplitLayout } from '../overlays/overlay-split-layout'
import { OverlayView } from '../overlays/overlay-view'
import { ARTIFACTS_ROUTE, MESSAGING_ROUTE, NEW_CHAT_ROUTE, SETTINGS_ROUTE, SKILLS_ROUTE } from '../routes'

export type CommandCenterSection = 'sessions' | 'system' | 'usage'

const SECTIONS = ['sessions', 'system', 'usage'] as const satisfies readonly CommandCenterSection[]

const USAGE_PERIODS = [7, 30, 90] as const
type UsagePeriod = (typeof USAGE_PERIODS)[number]

interface CommandCenterViewProps {
  initialSection?: CommandCenterSection
  onClose: () => void
  onDeleteSession: (sessionId: string) => Promise<void>
  onNavigateRoute: (path: string) => void
  onOpenSession: (sessionId: string) => void
}

const SECTION_LABELS: Record<CommandCenterSection, string> = {
  sessions: 'Sessions',
  system: 'System',
  usage: 'Usage'
}

const SECTION_DESCRIPTIONS: Record<CommandCenterSection, string> = {
  sessions: 'Search and manage sessions',
  system: 'Status, logs, and system actions',
  usage: 'Token, cost, and skill activity over time'
}

interface NavigationSearchEntry {
  detail?: string
  id: string
  route: string
  title: string
}

interface SectionSearchEntry {
  detail?: string
  id: string
  section: CommandCenterSection
  title: string
}

const NAVIGATION_SEARCH_ENTRIES: readonly NavigationSearchEntry[] = [
  { id: 'nav-new-chat', route: NEW_CHAT_ROUTE, title: 'New session', detail: 'Start a fresh session' },
  ...(IS_LOCKED_DEMO
    ? []
    : [{ id: 'nav-settings', route: SETTINGS_ROUTE, title: 'Settings', detail: 'Configure TchuekaM desktop' }]),
  { id: 'nav-skills', route: SKILLS_ROUTE, title: 'Skills & Tools', detail: 'Enable skills, toolsets, and providers' },
  ...(IS_LOCKED_DEMO
    ? []
    : [
        {
          id: 'nav-messaging',
          route: MESSAGING_ROUTE,
          title: 'Messaging',
          detail: 'Set up Telegram, Slack, Discord, and more'
        }
      ]),
  { id: 'nav-artifacts', route: ARTIFACTS_ROUTE, title: 'Artifacts', detail: 'Browse generated outputs' }
]

const SECTION_SEARCH_ENTRIES: readonly SectionSearchEntry[] = [
  { id: 'section-sessions', section: 'sessions', title: 'Sessions panel', detail: 'Search, pin, and manage sessions' },
  { id: 'section-system', section: 'system', title: 'System panel', detail: 'Gateway status, logs, restart/update' },
  { id: 'section-usage', section: 'usage', title: 'Usage panel', detail: 'Token, cost, and skill activity' }
]

interface SessionSearchHit {
  detail?: string
  kind: 'session'
  sessionId: string
  snippet: string
  title: string
}

interface RouteSearchHit {
  detail?: string
  kind: 'route'
  route: string
  title: string
}

interface SectionSearchHit {
  detail?: string
  kind: 'section'
  section: CommandCenterSection
  title: string
}

type CommandCenterSearchResult = RouteSearchHit | SectionSearchHit | SessionSearchHit

interface CommandCenterSearchProvider {
  id: string
  label: string
  search: (query: string) => Promise<CommandCenterSearchResult[]>
}

interface CommandCenterSearchGroup {
  id: string
  label: string
  results: CommandCenterSearchResult[]
}

function formatTimestamp(value?: number | null): string {
  if (!value) {
    return ''
  }

  const date = new Date(value * 1000)

  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function splitSessionSearchResult(result: SessionSearchApiResult, sessionsById: Map<string, SessionInfo>) {
  const row = sessionsById.get(result.session_id)
  const title = row ? sessionTitle(row) : result.session_id
  const detail = [result.model, result.source].filter(Boolean).join(' · ')

  return { detail, title }
}

function matchesSearchQuery(query: string, ...values: Array<string | undefined>): boolean {
  const normalized = query.trim().toLowerCase()

  if (!normalized) {
    return true
  }

  return values.some(value => value?.toLowerCase().includes(normalized))
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs)

    return () => window.clearTimeout(id)
  }, [delayMs, value])

  return debounced
}

export function CommandCenterView({
  initialSection,
  onClose,
  onDeleteSession,
  onNavigateRoute,
  onOpenSession
}: CommandCenterViewProps) {
  const sessions = useStore($sessions)
  const pinnedSessionIds = useStore($pinnedSessionIds)

  const [section, setSection] = useRouteEnumParam('section', SECTIONS, initialSection ?? 'sessions')

  const [query, setQuery] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchGroups, setSearchGroups] = useState<CommandCenterSearchGroup[]>([])
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [systemLoading, setSystemLoading] = useState(false)
  const [systemError, setSystemError] = useState('')
  const [systemAction, setSystemAction] = useState<ActionStatusResponse | null>(null)
  const [usagePeriod, setUsagePeriod] = useState<UsagePeriod>(30)
  const [usage, setUsage] = useState<AnalyticsResponse | null>(null)
  const [usageLoading, setUsageLoading] = useState(false)
  const [usageError, setUsageError] = useState('')
  const searchRequestRef = useRef(0)
  const usageRequestRef = useRef(0)

  const debouncedQuery = useDebouncedValue(query.trim(), 180)

  const sessionsById = useMemo(() => new Map(sessions.map(session => [session.id, session])), [sessions])

  const filteredSessions = useMemo(
    () =>
      [...sessions].sort((a, b) => {
        const left = a.last_active || a.started_at || 0
        const right = b.last_active || b.started_at || 0

        return right - left
      }),
    [sessions]
  )

  const searchProviders = useMemo<readonly CommandCenterSearchProvider[]>(
    () => [
      {
        id: 'navigation',
        label: 'Navigate',
        search: async searchQuery => {
          const routeHits: RouteSearchHit[] = NAVIGATION_SEARCH_ENTRIES.filter(entry =>
            matchesSearchQuery(searchQuery, entry.title, entry.detail, entry.route)
          ).map(entry => ({
            detail: entry.detail,
            kind: 'route',
            route: entry.route,
            title: entry.title
          }))

          const sectionHits: SectionSearchHit[] = SECTION_SEARCH_ENTRIES.filter(entry =>
            matchesSearchQuery(searchQuery, entry.title, entry.detail, SECTION_LABELS[entry.section])
          ).map(entry => ({
            detail: entry.detail,
            kind: 'section',
            section: entry.section,
            title: entry.title
          }))

          return [...routeHits, ...sectionHits]
        }
      },
      {
        id: 'sessions',
        label: 'Sessions',
        search: async searchQuery => {
          const response = await searchSessions(searchQuery)

          return response.results.map(result => {
            const { detail, title } = splitSessionSearchResult(result, sessionsById)

            return {
              detail,
              kind: 'session',
              sessionId: result.session_id,
              snippet: result.snippet || '',
              title
            } satisfies SessionSearchHit
          })
        }
      }
    ],
    [sessionsById]
  )

  const refreshSystem = useCallback(async () => {
    setSystemLoading(true)
    setSystemError('')

    try {
      const [statusResult, logsResult] = await Promise.allSettled([
        getStatus(),
        IS_LOCKED_DEMO
          ? Promise.resolve({ lines: [] as string[] })
          : getLogs({
              file: 'agent',
              lines: 120
            })
      ])

      if (statusResult.status === 'fulfilled') {
        setStatus(statusResult.value)
      } else {
        setSystemError(
          statusResult.reason instanceof Error ? statusResult.reason.message : String(statusResult.reason)
        )
      }

      if (logsResult.status === 'fulfilled') {
        setLogs(logsResult.value.lines)
      } else if (!IS_LOCKED_DEMO && statusResult.status === 'fulfilled') {
        setSystemError(logsResult.reason instanceof Error ? logsResult.reason.message : String(logsResult.reason))
      }
    } finally {
      setSystemLoading(false)
    }
  }, [])

  const refreshUsage = useCallback(async (days: UsagePeriod) => {
    const requestId = usageRequestRef.current + 1
    usageRequestRef.current = requestId
    setUsageLoading(true)
    setUsageError('')

    try {
      const response = await getUsageAnalytics(days)

      if (usageRequestRef.current === requestId) {
        setUsage(response)
      }
    } catch (error) {
      if (usageRequestRef.current === requestId) {
        setUsageError(error instanceof Error ? error.message : String(error))
      }
    } finally {
      if (usageRequestRef.current === requestId) {
        setUsageLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    if (!debouncedQuery) {
      setSearchGroups([])
      setSearchLoading(false)

      return
    }

    const requestId = searchRequestRef.current + 1
    searchRequestRef.current = requestId
    setSearchLoading(true)

    void Promise.all(
      searchProviders.map(async provider => ({
        id: provider.id,
        label: provider.label,
        results: await provider.search(debouncedQuery)
      }))
    )
      .then(groups => {
        if (searchRequestRef.current === requestId) {
          setSearchGroups(groups.filter(group => group.results.length > 0))
        }
      })
      .catch(() => {
        if (searchRequestRef.current === requestId) {
          setSearchGroups([])
        }
      })
      .finally(() => {
        if (searchRequestRef.current === requestId) {
          setSearchLoading(false)
        }
      })
  }, [debouncedQuery, searchProviders])

  useEffect(() => {
    if (section === 'system' && !status && !systemLoading) {
      void refreshSystem()
    }
  }, [refreshSystem, section, status, systemLoading])

  useEffect(() => {
    if (section === 'usage') {
      void refreshUsage(usagePeriod)
    }
  }, [refreshUsage, section, usagePeriod])

  const showGlobalSearchResults = debouncedQuery.length > 0
  const hasGlobalSearchResults = searchGroups.length > 0
  const sessionListHasResults = filteredSessions.length > 0

  const runSystemAction = useCallback(
    async (kind: 'restart' | 'update') => {
      setSystemError('')

      try {
        const started = kind === 'restart' ? await restartGateway() : await updateHermes()
        let nextStatus: ActionStatusResponse | null = null

        for (let attempt = 0; attempt < 18; attempt += 1) {
          await new Promise(resolve => window.setTimeout(resolve, 1200))
          const polled = await getActionStatus(started.name, 180)
          nextStatus = polled
          setSystemAction(polled)
          upsertDesktopActionTask(polled)

          if (!polled.running) {
            break
          }
        }

        if (!nextStatus) {
          const pendingStatus = {
            exit_code: null,
            lines: ['Action started, waiting for status...'],
            name: started.name,
            pid: started.pid,
            running: true
          }

          setSystemAction(pendingStatus)
          upsertDesktopActionTask(pendingStatus)
        }
      } catch (error) {
        setSystemError(error instanceof Error ? error.message : String(error))
      } finally {
        void refreshSystem()
      }
    },
    [refreshSystem]
  )

  const handleSearchSelect = useCallback(
    (result: CommandCenterSearchResult) => {
      if (result.kind === 'route') {
        onNavigateRoute(result.route)

        return
      }

      if (result.kind === 'section') {
        setSection(result.section)
        setQuery('')

        return
      }

      onOpenSession(result.sessionId)
    },
    [onNavigateRoute, onOpenSession, setSection]
  )

  return (
    <OverlayView
      closeLabel="Close command center"
      headerContent={
        <OverlaySearchInput
          containerClassName="w-full sm:w-[min(36rem,calc(100vw-16rem))] md:w-[min(36rem,calc(100vw-24rem))]"
          loading={searchLoading}
          onChange={next => setQuery(next)}
          placeholder="Search sessions, views, and actions"
          value={query}
        />
      }
      onClose={onClose}
    >
      <OverlaySplitLayout>
        <OverlaySidebar>
          {SECTIONS.map(value => (
            <OverlayNavItem
              active={section === value}
              icon={value === 'sessions' ? Pin : value === 'system' ? Activity : BarChart3}
