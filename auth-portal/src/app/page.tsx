'use client'

import { useAuth } from '../contexts/AuthContext'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect } from 'react'
import { getDesktopLaunchUrl } from '../lib/redirect'
import {
  LogOut,
  Building2,
  Mail,
  User,
  Key,
  Database,
  Activity,
  ArrowUpRight,
  Cpu,
  Bot,
  Terminal,
  Radio,
  BookOpen,
  Sparkles,
  BarChart3,
  Rocket,
  CheckCircle2,
} from 'lucide-react'

export default function Home() {
  const { user, session, profile, logout, loading, isAdmin, trackEvent } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login')
    }
  }, [user, loading, router])

  const handleLogout = async () => {
    await logout()
    router.push('/login')
  }

  const desktopLaunchUrl = getDesktopLaunchUrl(session)

  const handleLaunchDesktop = () => {
    if (!desktopLaunchUrl) return
    trackEvent('desktop_handoff', { metadata: { target: desktopLaunchUrl.split('#')[0] } })
    window.location.assign(desktopLaunchUrl)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-100">
        <div className="text-center space-y-4">
          <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs text-slate-400 font-medium">
            Validating Tchuekam Agent Session & PostgreSQL Permissions...
          </p>
        </div>
      </div>
    )
  }

  if (!user) {
    return null
  }

  const displayName =
    profile?.full_name ||
    user.user_metadata?.full_name ||
    profile?.username ||
    user.email?.split('@')[0] ||
    'Agent Architect'
  const displayOrg =
    profile?.company_name || user.user_metadata?.company_name || 'Giantech Empire'
  const displayRole = profile?.role || 'Agent Architect'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navigation */}
      <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-amber-400 p-0.5 flex items-center justify-center shadow-md shadow-amber-500/10">
              <div className="w-full h-full bg-slate-950 rounded-[9px] flex items-center justify-center">
                <span className="text-amber-400 font-bold text-sm select-none">☤</span>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-sm tracking-tight text-white">
                  Tchuekam Agent
                </span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  GIANTECH
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 sm:gap-3">
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-slate-300 font-medium">eu-central-1 (Tchuekam-tech)</span>
            </div>

            {isAdmin && (
              <Link
                href="/tracking"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-300 text-xs font-semibold transition"
              >
                <BarChart3 className="w-3.5 h-3.5" />
                <span>User Tracking</span>
              </Link>
            )}

            {desktopLaunchUrl && (
              <button
                onClick={handleLaunchDesktop}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition"
              >
                <Rocket className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Launch Desktop UI</span>
              </button>
            )}

            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white text-xs font-semibold transition"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Sign Out</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Welcome Banner */}
        <div className="relative rounded-2xl bg-gradient-to-r from-slate-900 via-purple-950/40 to-slate-900 border border-slate-800 p-6 sm:p-8 overflow-hidden shadow-2xl">
          <div className="absolute top-0 right-0 w-80 h-80 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />
          <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[11px] font-semibold">
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                <span>Autonomous Agent Control Plane Initialized</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                Welcome back, {displayName}
              </h1>
              <p className="text-xs sm:text-sm text-slate-400 max-w-2xl">
                Workspace: <span className="text-amber-400 font-semibold">{displayOrg}</span> •
                Role: <span className="text-slate-300 font-semibold">{displayRole}</span>. Your
                Supabase PostgreSQL database is active with Row-Level Security and auth event
                tracking.
              </p>
            </div>

            <div className="flex flex-wrap gap-2.5">
              {desktopLaunchUrl && (
                <button
                  onClick={handleLaunchDesktop}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-indigo-600 hover:from-amber-400 hover:to-indigo-500 text-white text-xs font-bold shadow-lg transition"
                >
                  <Rocket className="w-4 h-4" />
                  <span>Open Tchuekam Agent Console</span>
                </button>
              )}
              {isAdmin && (
                <Link
                  href="/tracking"
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition"
                >
                  <Activity className="w-4 h-4 text-amber-400" />
                  <span>Open User Tracking Console</span>
                </Link>
              )}
            </div>
          </div>
        </div>

        {/* Status Metrics */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
            <div className="flex items-center justify-between text-slate-400 text-xs">
              <span>Agent Learning Loop</span>
              <Sparkles className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-xl font-bold text-white">Active ☤</div>
            <p className="text-[11px] text-slate-500">Autonomous skill creation enabled</p>
          </div>

          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
            <div className="flex items-center justify-between text-slate-400 text-xs">
              <span>Database Instance</span>
              <Database className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-xl font-bold text-white truncate">fzoiiusuqvjhwivstbyb</div>
            <p className="text-[11px] text-emerald-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              ACTIVE_HEALTHY (RLS)
            </p>
          </div>

          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
            <div className="flex items-center justify-between text-slate-400 text-xs">
              <span>Tracked Sign-Ins</span>
              <Cpu className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="text-xl font-bold text-white">{profile?.login_count ?? 1}</div>
            <p className="text-[11px] text-slate-500">Audited in public.auth_events</p>
          </div>

          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
            <div className="flex items-center justify-between text-slate-400 text-xs">
              <span>Email Delivery</span>
              <Radio className="w-4 h-4 text-purple-400" />
            </div>
            <div className="text-xl font-bold text-white">Resend SMTP</div>
            <p className="text-[11px] text-emerald-400">auth@tchuekam.com verified</p>
          </div>
        </div>

        {/* User Identity Details & Connected Services */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Identity Card */}
          <div className="lg:col-span-2 rounded-xl bg-slate-900/60 border border-slate-800/80 p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-sm font-semibold text-white">Agent Architect Profile</h3>
                <p className="text-xs text-slate-400">
                  Stored in Supabase <code className="text-amber-400">public.profiles</code> with
                  PostgreSQL RLS.
                </p>
              </div>
              <span className="inline-flex items-center gap-1 text-[10px] px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 font-semibold uppercase tracking-wider">
                <CheckCircle2 className="w-3 h-3" />
                {user.email_confirmed_at ? 'Email Verified' : 'PostgreSQL RLS'}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                <div className="text-slate-500 text-[11px] flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5" /> Full Name
                </div>
                <div className="font-semibold text-white">{displayName}</div>
              </div>

              <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                <div className="text-slate-500 text-[11px] flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5" /> Work Email
                </div>
                <div className="font-semibold text-white truncate">{user.email}</div>
              </div>

              <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                <div className="text-slate-500 text-[11px] flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5" /> Organization
                </div>
                <div className="font-semibold text-white">{displayOrg}</div>
              </div>

              <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                <div className="text-slate-500 text-[11px] flex items-center gap-1.5">
                  <Key className="w-3.5 h-3.5" /> User UUID
                </div>
                <div className="font-mono text-[11px] text-slate-300 truncate">{user.id}</div>
              </div>
            </div>

            <div className="pt-2 text-xs text-slate-400 flex items-center justify-between border-t border-slate-800/80">
              <span>
                Last Signed In:{' '}
                {user.last_sign_in_at ? new Date(user.last_sign_in_at).toLocaleString() : 'Just now'}
              </span>
              <span className="text-emerald-400 font-medium">Session Valid</span>
            </div>
          </div>

          {/* Quick Resources */}
          <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-6 space-y-4">
            <h3 className="text-sm font-semibold text-white">Tchuekam Agent Resources</h3>
            <div className="space-y-3">
              {isAdmin && (
                <Link
                  href="/tracking"
                  className="p-3 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 flex items-center justify-between transition group"
                >
                  <div className="flex items-center gap-2.5">
                    <BarChart3 className="w-4 h-4 text-amber-400" />
                    <div>
                      <div className="text-xs font-semibold text-white group-hover:text-amber-300 transition">
                        Live User & Login Tracking
                      </div>
                      <div className="text-[10px] text-amber-200/70">
                        View signups, verifications & CSV export
                      </div>
                    </div>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-amber-400 transition" />
                </Link>
              )}

              <a
                href="https://github.com/Tchuekam/tchuekam-desktop"
                target="_blank"
                rel="noreferrer"
                className="p-3 rounded-lg bg-slate-950 hover:bg-slate-900 border border-slate-800 flex items-center justify-between transition group"
              >
                <div className="flex items-center gap-2.5">
                  <Terminal className="w-4 h-4 text-amber-400" />
                  <div>
                    <div className="text-xs font-semibold text-white group-hover:text-amber-400 transition">
                      Tchuekam Desktop Repo
                    </div>
                    <div className="text-[10px] text-slate-500">
                      github.com/Tchuekam/tchuekam-desktop
                    </div>
                  </div>
                </div>
                <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 transition" />
              </a>

              <a
                href="https://docs.tchuekam.com/docs/"
                target="_blank"
                rel="noreferrer"
                className="p-3 rounded-lg bg-slate-950 hover:bg-slate-900 border border-slate-800 flex items-center justify-between transition group"
              >
                <div className="flex items-center gap-2.5">
                  <BookOpen className="w-4 h-4 text-indigo-400" />
                  <div>
                    <div className="text-xs font-semibold text-white group-hover:text-indigo-400 transition">
                      Documentation
                    </div>
                    <div className="text-[10px] text-slate-500">docs.tchuekam.com</div>
                  </div>
                </div>
                <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-indigo-400 transition" />
              </a>

              <a
                href="https://tchuekam.com"
                target="_blank"
                rel="noreferrer"
                className="p-3 rounded-lg bg-slate-950 hover:bg-slate-900 border border-slate-800 flex items-center justify-between transition group"
              >
                <div className="flex items-center gap-2.5">
                  <Bot className="w-4 h-4 text-purple-400" />
                  <div>
                    <div className="text-xs font-semibold text-white group-hover:text-purple-400 transition">
                      Giantech Empire
                    </div>
                    <div className="text-[10px] text-slate-500">tchuekam.com</div>
                  </div>
                </div>
                <ArrowUpRight className="w-4 h-4 text-slate-500 group-hover:text-purple-400 transition" />
              </a>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
