'use client'

import { useEffect, useState, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '../../contexts/AuthContext'
import {
  Users,
  CheckCircle2,
  Clock,
  Activity,
  Search,
  Download,
  RefreshCw,
  ArrowLeft,
  ShieldAlert,
  LogIn,
  UserPlus,
  MailCheck,
  Sparkles,
  LogOut,
} from 'lucide-react'

interface TrackingSummary {
  totalUsers: number
  verifiedUsers: number
  unverifiedUsers: number
  totalLogins: number
  signupsLast7Days: number
  eventsLast24Hours: number
}

interface TrackedUser {
  id: string
  email: string
  full_name: string | null
  username: string | null
  company_name: string | null
  role: string | null
  email_confirmed_at: string | null
  last_sign_in_at: string | null
  login_count: number
  signup_source: string | null
  provider: string | null
  created_at: string
}

interface AuthEventRow {
  id: string
  user_id: string | null
  email: string
  event_type: string
  provider: string | null
  ip_address: string | null
  user_agent: string | null
  source: string | null
  metadata: Record<string, unknown> | null
  created_at: string
}

export default function TrackingPage() {
  const { user, session, loading, isAdmin, logout } = useAuth()
  const router = useRouter()

  const [dataLoading, setDataLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<TrackingSummary | null>(null)
  const [usersList, setUsersList] = useState<TrackedUser[]>([])
  const [eventsList, setEventsList] = useState<AuthEventRow[]>([])

  const [search, setSearch] = useState('')
  const [verifiedFilter, setVerifiedFilter] = useState<'all' | 'verified' | 'pending'>('all')
  const [eventFilter, setEventFilter] = useState<string>('all')
  const [activeTab, setActiveTab] = useState<'users' | 'events'>('users')

  const loadTelemetry = useCallback(
    async (isManual = false) => {
      if (!session?.access_token) return
      if (isManual) setRefreshing(true)
      else setDataLoading(true)
      setError(null)

      try {
        const res = await fetch('/api/admin/tracking', {
          headers: { Authorization: `Bearer ${session.access_token}` },
          cache: 'no-store',
        })
        const json = await res.json()
        if (!res.ok) {
          throw new Error(json?.error || `HTTP ${res.status}`)
        }
        setSummary(json.summary)
        setUsersList(json.users || [])
        setEventsList(json.events || [])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to load tracking telemetry')
      } finally {
        setDataLoading(false)
        setRefreshing(false)
      }
    },
    [session?.access_token]
  )

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login?redirect_to=/tracking')
    }
  }, [loading, user, router])

  useEffect(() => {
    if (session?.access_token && isAdmin) {
      loadTelemetry(false)
    } else if (!loading) {
      setDataLoading(false)
    }
  }, [session?.access_token, isAdmin, loading, loadTelemetry])

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase()
    return usersList.filter((u) => {
      if (verifiedFilter === 'verified' && !u.email_confirmed_at) return false
      if (verifiedFilter === 'pending' && u.email_confirmed_at) return false
      if (!q) return true
      return (
        u.email.toLowerCase().includes(q) ||
        (u.full_name || '').toLowerCase().includes(q) ||
        (u.username || '').toLowerCase().includes(q) ||
        (u.company_name || '').toLowerCase().includes(q)
      )
    })
  }, [usersList, search, verifiedFilter])

  const filteredEvents = useMemo(() => {
    const q = search.trim().toLowerCase()
    return eventsList.filter((e) => {
      if (eventFilter !== 'all' && e.event_type !== eventFilter) return false
      if (!q) return true
      return (
        e.email.toLowerCase().includes(q) ||
        e.event_type.toLowerCase().includes(q) ||
        (e.source || '').toLowerCase().includes(q)
      )
    })
  }, [eventsList, search, eventFilter])

  const exportUsersCsv = () => {
    const headers = [
      'id',
      'email',
      'full_name',
      'username',
      'company_name',
      'role',
      'verified',
      'login_count',
      'last_sign_in_at',
      'signup_source',
      'created_at',
    ]
    const escape = (val: unknown) => {
      const raw = String(val ?? '')
      const neutralized = /^[=+\-@\t\r]/.test(raw) ? `'${raw}` : raw
      const s = neutralized.replace(/"/g, '""')
      return `"${s}"`
    }
    const rows = filteredUsers.map((u) =>
      [
        u.id,
        u.email,
        u.full_name || '',
        u.username || '',
        u.company_name || '',
        u.role || '',
        u.email_confirmed_at ? 'verified' : 'pending',
        u.login_count,
        u.last_sign_in_at || '',
        u.signup_source || '',
        u.created_at,
      ]
        .map(escape)
        .join(',')
    )
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tchuekam-agent-users-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  if (loading || !user) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-300 text-xs">
        Validating administrator session...
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center mx-auto text-red-400">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <h1 className="text-lg font-bold text-white">Administrator Access Restricted</h1>
          <p className="text-xs text-slate-400">
            Signed in as <span className="text-slate-200 font-semibold">{user.email}</span>. User
            analytics and sign-in telemetry are restricted to administrators.
          </p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back to Control Plane
          </Link>
        </div>
      </div>
    )
  }

  const eventBadge = (type: string) => {
    const map: Record<string, string> = {
      signup: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
      login: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
      email_verified: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
      magic_link_sent: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
      password_reset_requested: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
      password_updated: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
      verification_resent: 'bg-slate-700/60 text-slate-300 border-slate-600',
      desktop_handoff: 'bg-teal-500/15 text-teal-300 border-teal-500/30',
      logout: 'bg-slate-800 text-slate-400 border-slate-700',
    }
    return map[type] || 'bg-slate-800 text-slate-300 border-slate-700'
  }

  const verifiedRate =
    summary && summary.totalUsers > 0
      ? Math.round((summary.verifiedUsers / summary.totalUsers) * 100)
      : 0

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-800/80 bg-slate-950/85 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs text-slate-300 transition"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Control Plane</span>
            </Link>
            <div className="flex items-center gap-2">
              <span className="text-amber-400 font-bold text-base">☤</span>
              <span className="font-extrabold text-sm text-white">Tchuekam User Tracking</span>
              <span className="hidden sm:inline-block text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                ADMIN TELEMETRY
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => loadTelemetry(true)}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs text-slate-200 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
            <button
