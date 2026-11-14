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
    URL.revokeObjectURL(url)
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
              onClick={exportUsersCsv}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition"
            >
              <Download className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Export CSV</span>
            </button>
            <button
              onClick={async () => {
                await logout()
                router.push('/login')
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 text-xs transition"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs">
            {error}
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Total Users</span>
              <Users className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="text-2xl font-extrabold text-white">
              {dataLoading ? '...' : summary?.totalUsers ?? 0}
            </div>
            <p className="text-[11px] text-slate-500">Registered in Supabase Auth</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Email Verified</span>
              <MailCheck className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-extrabold text-white">
              {dataLoading ? '...' : summary?.verifiedUsers ?? 0}
            </div>
            <p className="text-[11px] text-emerald-400">{verifiedRate}% confirmation rate</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Total Sign-Ins</span>
              <LogIn className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-2xl font-extrabold text-white">
              {dataLoading ? '...' : summary?.totalLogins ?? 0}
            </div>
            <p className="text-[11px] text-slate-500">Tracked session grants</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>New Signups (7d)</span>
              <UserPlus className="w-4 h-4 text-purple-400" />
            </div>
            <div className="text-2xl font-extrabold text-white">
              {dataLoading ? '...' : summary?.signupsLast7Days ?? 0}
            </div>
            <p className="text-[11px] text-slate-500">
              {summary?.unverifiedUsers ?? 0} pending verification
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Events (24h)</span>
              <Activity className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="text-2xl font-extrabold text-white">
              {dataLoading ? '...' : summary?.eventsLast24Hours ?? 0}
            </div>
            <p className="text-[11px] text-slate-500">PostgreSQL trigger + portal telemetry</p>
          </div>
        </div>

        {/* Search, Filter & Tabs */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-slate-900/50 border border-slate-800 rounded-xl p-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('users')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeTab === 'users'
                  ? 'bg-amber-500 text-slate-950'
                  : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              Users Directory ({filteredUsers.length})
            </button>
            <button
              onClick={() => setActiveTab('events')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeTab === 'events'
                  ? 'bg-amber-500 text-slate-950'
                  : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              Auth Activity Feed ({filteredEvents.length})
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter by email, name, workspace..."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
              />
            </div>

            {activeTab === 'users' ? (
              <select
                value={verifiedFilter}
                onChange={(e) => setVerifiedFilter(e.target.value as 'all' | 'verified' | 'pending')}
                className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none"
              >
                <option value="all">All Statuses</option>
                <option value="verified">Verified Only</option>
                <option value="pending">Pending Verification</option>
              </select>
            ) : (
              <select
                value={eventFilter}
                onChange={(e) => setEventFilter(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none"
              >
                <option value="all">All Events</option>
                <option value="signup">signup</option>
                <option value="login">login</option>
                <option value="email_verified">email_verified</option>
                <option value="magic_link_sent">magic_link_sent</option>
                <option value="verification_resent">verification_resent</option>
                <option value="password_reset_requested">password_reset_requested</option>
                <option value="password_updated">password_updated</option>
                <option value="desktop_handoff">desktop_handoff</option>
                <option value="logout">logout</option>
              </select>
            )}
          </div>
        </div>

        {/* Table Panels */}
        {activeTab === 'users' ? (
          <div className="rounded-xl bg-slate-900/60 border border-slate-800 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/90 text-[11px] uppercase tracking-wider text-slate-400">
                    <th className="py-3 px-4">User / Email</th>
                    <th className="py-3 px-4">Workspace & Role</th>
                    <th className="py-3 px-4">Verification</th>
                    <th className="py-3 px-4">Logins</th>
                    <th className="py-3 px-4">Last Sign-In</th>
                    <th className="py-3 px-4">Joined</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {filteredUsers.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-900/80 transition">
                      <td className="py-3 px-4">
                        <div className="font-semibold text-white">{u.full_name || u.username || 'Unnamed User'}</div>
                        <div className="text-[11px] text-slate-400">{u.email}</div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="text-slate-200">{u.company_name || 'Giantech Empire'}</div>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                              (u.role || '').toLowerCase() === 'admin'
                                ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                                : 'bg-slate-800 text-slate-300'
                            }`}
                          >
                            {u.role || 'Agent Architect'}
                          </span>
                          <span className="text-[10px] text-slate-500">{u.signup_source}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        {u.email_confirmed_at ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-[11px]">
                            <CheckCircle2 className="w-3 h-3" /> Verified
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px]">
                            <Clock className="w-3 h-3" /> Pending
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-slate-200">
                        {u.login_count}
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {u.last_sign_in_at ? new Date(u.last_sign_in_at).toLocaleString() : 'Never'}
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                  {filteredUsers.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-10 text-center text-slate-500">
                        {dataLoading ? 'Loading tracked users...' : 'No matching users found.'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="rounded-xl bg-slate-900/60 border border-slate-800 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/90 text-[11px] uppercase tracking-wider text-slate-400">
                    <th className="py-3 px-4">Event</th>
                    <th className="py-3 px-4">Email</th>
                    <th className="py-3 px-4">Provider / Source</th>
                    <th className="py-3 px-4">IP Address</th>
                    <th className="py-3 px-4">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {filteredEvents.map((ev) => (
                    <tr key={ev.id} className="hover:bg-slate-900/80 transition">
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] font-semibold ${eventBadge(
                            ev.event_type
                          )}`}
                        >
                          <Sparkles className="w-2.5 h-2.5" />
                          {ev.event_type}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-medium text-white">{ev.email}</td>
                      <td className="py-3 px-4 text-slate-400">
                        {ev.provider || 'email'} · {ev.source || 'auth-portal'}
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-slate-400">
                        {ev.ip_address || '—'}
                      </td>
                      <td className="py-3 px-4 text-slate-400">
                        {new Date(ev.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                  {filteredEvents.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-10 text-center text-slate-500">
                        {dataLoading ? 'Loading event stream...' : 'No auth events recorded yet.'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
