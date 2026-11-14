'use client'

import { Suspense, useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '../../contexts/AuthContext'
import { OAuthButtons } from '../../components/OAuthButtons'
import { resolvePostAuthDestination } from '../../lib/redirect'
import {
  Lock,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  ArrowRight,
  Server,
  RefreshCw,
  CheckCircle2,
  ExternalLink,
  Sparkles,
} from 'lucide-react'

function LoginPageInner() {
  const {
    login,
    signInWithMagicLink,
    resetPassword,
    resendVerification,
    user,
    session,
    error: authError,
    loading: authLoading,
    clearError,
    trackEvent,
  } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()

  const redirectTo = searchParams.get('redirect_to') || searchParams.get('next')
  const verifiedNotice = searchParams.get('verified') === 'true'

  const [authMode, setAuthMode] = useState<'password' | 'magic'>('password')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [magicLinkSent, setMagicLinkSent] = useState(false)

  // Forgot password & unconfirmed resend flows
  const [forgotPasswordOpen, setForgotPasswordOpen] = useState(false)
  const [resetSent, setResetSent] = useState(false)
  const [resetEmail, setResetEmail] = useState('')
  const [resetSubmitting, setResetSubmitting] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  const [resendingUnconfirmed, setResendingUnconfirmed] = useState(false)
  const [resendUnconfirmedMsg, setResendUnconfirmedMsg] = useState<string | null>(null)

  useEffect(() => {
    if (user && session) {
      const { url, external } = resolvePostAuthDestination(redirectTo, session)
      if (external) {
        trackEvent('desktop_handoff', { metadata: { target: redirectTo } })
        window.location.assign(url)
      } else {
        router.replace(url)
      }
    }
  }, [user, session, redirectTo, router, trackEvent])

  useEffect(() => {
    clearError()
  }, [clearError])

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setResendUnconfirmedMsg(null)
    clearError()

    if (!email.trim() || !password) {
      setFormError('Email and password are required.')
      return
    }

    setIsSubmitting(true)
    await login(email, password)
    setIsSubmitting(false)
  }

  const handleMagicSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setResendUnconfirmedMsg(null)
    clearError()

    if (!email.trim()) {
      setFormError('Please enter your work email address.')
      return
    }

    setIsSubmitting(true)
    const result = await signInWithMagicLink(email, redirectTo || undefined)
    setIsSubmitting(false)

    if (result.success) {
      setMagicLinkSent(true)
    } else if (result.error) {
      setFormError(result.error)
    }
  }

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resetEmail.trim()) return

    setResetError(null)
    setResetSubmitting(true)
    const result = await resetPassword(resetEmail)
    setResetSubmitting(false)

    if (result.success) {
      setResetSent(true)
    } else {
      setResetError(result.error || 'Failed to dispatch password recovery link.')
    }
  }

  const handleResendUnconfirmed = async () => {
    if (!email.trim() || resendingUnconfirmed) return
    setResendingUnconfirmed(true)
    setResendUnconfirmedMsg(null)
    const res = await resendVerification(email, redirectTo || undefined)
    setResendingUnconfirmed(false)
    if (res.success) {
      setResendUnconfirmedMsg('Confirmation email sent from auth@tchuekam.com. Check your inbox.')
    } else {
      setFormError(res.error || 'Could not resend confirmation email right now.')
    }
  }

  const registerHref = redirectTo
    ? `/register?redirect_to=${encodeURIComponent(redirectTo)}`
    : '/register'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex">
      {/* LEFT COLUMN: Tchuekam Agent Value Prop & Branding */}
      <div className="hidden lg:flex lg:w-5/12 xl:w-1/2 flex-col justify-between p-12 bg-gradient-to-br from-slate-950 via-indigo-950/70 to-slate-900 border-r border-slate-800/80 relative overflow-hidden">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-10 right-10 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 space-y-6">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-amber-400 p-0.5 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                <span className="text-amber-400 font-bold text-lg select-none">☤</span>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-lg tracking-tight text-white">Tchuekam Agent</span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  GIANTECH EMPIRE
                </span>
              </div>
              <p className="text-[11px] text-slate-400">Self-Improving Autonomous AI Architecture</p>
            </div>
          </div>

          <div className="pt-6 space-y-4 max-w-lg">
            <h1 className="text-3xl xl:text-4xl font-extrabold tracking-tight text-white leading-tight">
              Tchuekam Agent Management & Orchestration Console
            </h1>
            <p className="text-slate-400 text-sm leading-relaxed">
              Authenticate into your autonomous agent control plane. Supervise self-learning memory,
              manage multi-channel gateways, and configure dynamic skill synthesis.
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-3 p-3.5 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-md">
              <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 shrink-0 font-bold">
                ☤
              </div>
              <div>
                <p className="text-xs font-semibold text-white">Closed-Loop Memory Loop</p>
                <p className="text-[11px] text-slate-400">
                  Continuous skill synthesis and FTS5 conversational recall.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3.5 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-md">
              <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
                <Server className="w-5 h-5" />
              </div>
              <div>
                <p className="text-xs font-semibold text-white">PostgreSQL Cluster Active</p>
                <p className="text-[11px] text-slate-400">
                  Tchuekam-tech database mesh with strict tenant isolation.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="relative z-10 pt-8 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-slate-400">Enterprise Tenant Active (eu-central-1)</span>
          </div>
          <a
            href="https://github.com/Tchuekam/tchuekam-desktop"
            target="_blank"
            rel="noreferrer"
            className="hover:text-slate-300 transition flex items-center gap-1"
          >
            GitHub Repo <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* RIGHT COLUMN: Sign In Form */}
      <div className="flex-1 flex flex-col justify-center px-6 sm:px-12 lg:px-16 xl:px-24 py-12">
        <div className="w-full max-w-md mx-auto space-y-6">
          <div className="space-y-1">
            <div className="lg:hidden flex items-center gap-2 mb-4">
              <span className="text-amber-400 font-bold text-xl select-none">☤</span>
              <span className="font-bold text-white">Tchuekam Agent</span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-purple-500/20 text-purple-300">
                Giantech
              </span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
              Sign In to Console
            </h2>
            <p className="text-xs sm:text-sm text-slate-400">
              {redirectTo
                ? 'Authenticate to continue back to your Tchuekam Agent workspace.'
                : 'Enter your credentials or request an instant sign-in link.'}
            </p>
          </div>

          {verifiedNotice && (
            <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs">
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-emerald-400" />
              <span>Email verified! Sign in below to enter your Tchuekam Agent console.</span>
            </div>
          )}

          <OAuthButtons redirectTo={redirectTo} dividerText="Or sign in with work email" />

          {/* Sign-In Mode Switcher: Password vs Magic Link */}
          <div className="grid grid-cols-2 p-1 rounded-xl bg-slate-900 border border-slate-800 text-xs">
            <button
              type="button"
              onClick={() => {
                setAuthMode('password')
                setMagicLinkSent(false)
                setFormError(null)
              }}
              className={`py-2 rounded-lg font-semibold transition ${
                authMode === 'password'
                  ? 'bg-slate-800 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Password
            </button>
            <button
              type="button"
              onClick={() => {
                setAuthMode('magic')
                setFormError(null)
              }}
              className={`py-2 rounded-lg font-semibold transition flex items-center justify-center gap-1.5 ${
                authMode === 'magic'
                  ? 'bg-slate-800 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span>Magic Link</span>
            </button>
          </div>

          {/* Error Message */}
          {(formError || authError) && (
            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-red-400" />
              <div className="flex-1 space-y-2">
                <div className="font-medium">{formError || authError}</div>
                {(formError || authError || '').toLowerCase().includes('confirm') && email.trim() && (
                  <button
                    type="button"
                    onClick={handleResendUnconfirmed}
                    disabled={resendingUnconfirmed}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-300 font-semibold transition"
                  >
                    {resendingUnconfirmed ? 'Sending confirmation...' : 'Resend confirmation email'}
                  </button>
                )}
              </div>
            </div>
          )}

          {resendUnconfirmedMsg && (
            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs">
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-emerald-400" />
              <span className="font-medium">{resendUnconfirmedMsg}</span>
            </div>
          )}

          {authMode === 'password' ? (
            <form onSubmit={handlePasswordSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Work Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="email"
                    required
                    placeholder="name@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-medium text-slate-300">Password</label>
                  <button
                    type="button"
                    onClick={() => {
                      setForgotPasswordOpen(true)
                      setResetEmail(email)
                    }}
                    className="text-[11px] text-amber-400 hover:text-amber-300 transition"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    placeholder="••••••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-10 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-200 transition"
                  >
                    {showPassword ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4 text-slate-400" />
                    )}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting || authLoading}
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-amber-500 via-indigo-600 to-purple-600 hover:from-amber-400 hover:to-purple-500 text-white font-semibold text-xs tracking-wide shadow-lg shadow-amber-500/20 transition disabled:opacity-50 disabled:cursor-not-allowed mt-2"
              >
                {isSubmitting || authLoading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Verifying Agent Credentials...</span>
                  </>
                ) : (
                  <>
                    <span>Sign In to Console</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>
          ) : magicLinkSent ? (
            <div className="p-5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 space-y-3 text-xs">
              <div className="flex items-center gap-2 text-emerald-300 font-semibold">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Sign-in link dispatched via Resend</span>
              </div>
              <p className="text-slate-300 leading-relaxed">
                Check <strong className="text-white">{email}</strong> and click the one-time
                sign-in button to access Tchuekam Agent without typing a password.
              </p>
              <button
                type="button"
                onClick={() => setMagicLinkSent(false)}
                className="text-amber-400 hover:text-amber-300 font-semibold underline"
              >
                Send to another email
              </button>
            </div>
          ) : (
            <form onSubmit={handleMagicSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Work Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="email"
                    required
                    placeholder="name@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition"
                  />
                </div>
                <p className="mt-1.5 text-[11px] text-slate-500">
                  Works for both existing accounts and instant first-time registration.
                </p>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-semibold text-xs tracking-wide shadow-lg transition disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Sending One-Time Link...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Email Me a Sign-In Link</span>
                  </>
                )}
              </button>
            </form>
          )}

          {/* Switch to Register */}
          <div className="text-center text-xs text-slate-400 pt-2 border-t border-slate-800">
            Don&apos;t have an agent account?{' '}
            <Link
              href={registerHref}
              className="text-amber-400 hover:text-amber-300 font-semibold underline-offset-4 hover:underline"
            >
              Create Tchuekam Agent Account
            </Link>
          </div>
        </div>
      </div>

      {/* Forgot Password Modal */}
      {forgotPasswordOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-sm w-full space-y-4 shadow-2xl">
            <div className="space-y-1">
              <h3 className="text-base font-bold text-white">Reset Agent Password</h3>
              <p className="text-xs text-slate-400">
                Enter your work email address to receive password recovery instructions.
              </p>
            </div>

            {resetSent ? (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-300 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Recovery link dispatched! Check your email.</span>
              </div>
            ) : (
              <form onSubmit={handleResetPassword} className="space-y-3">
                {resetError && (
                  <div className="p-2.5 bg-red-500/10 border border-red-500/30 rounded-xl text-red-300 text-xs flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                    <span>{resetError}</span>
                  </div>
                )}
                <input
                  type="email"
                  required
                  placeholder="name@company.com"
                  value={resetEmail}
                  onChange={(e) => {
                    setResetEmail(e.target.value)
                    if (resetError) setResetError(null)
                  }}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                />
                <button
                  type="submit"
                  disabled={resetSubmitting}
                  className="w-full py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold transition"
                >
                  {resetSubmitting ? 'Sending Link...' : 'Send Reset Link'}
                </button>
              </form>
            )}

            <button
              type="button"
              onClick={() => {
                setForgotPasswordOpen(false)
                setResetSent(false)
              }}
              className="w-full text-center text-xs text-slate-400 hover:text-slate-200 transition"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 text-xs">
          Loading Tchuekam Agent Sign In...
        </div>
      }
    >
      <LoginPageInner />
    </Suspense>
  )
}
