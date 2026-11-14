'use client'

import { Suspense, useState, useEffect, useMemo } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '../../contexts/AuthContext'
import { OAuthButtons } from '../../components/OAuthButtons'
import { resolvePostAuthDestination } from '../../lib/redirect'
import {
  Lock,
  Mail,
  User,
  Building2,
  AtSign,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Server,
  ExternalLink,
  RefreshCw,
  Cpu,
  Send,
} from 'lucide-react'

function RegisterPageInner() {
  const {
    register,
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

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [agreeTerms, setAgreeTerms] = useState(false)

  const [formError, setFormError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [verificationRequired, setVerificationRequired] = useState(false)
  const [registeredEmail, setRegisteredEmail] = useState('')

  const [resending, setResending] = useState(false)
  const [resendCooldown, setResendCooldown] = useState(0)
  const [resendMessage, setResendMessage] = useState<string | null>(null)

  useEffect(() => {
    if (user && session && !verificationRequired) {
      const { url, external } = resolvePostAuthDestination(redirectTo, session)
      if (external) {
        trackEvent('desktop_handoff', { metadata: { target: redirectTo } })
        window.location.assign(url)
      } else {
        router.replace(url)
      }
    }
  }, [user, session, verificationRequired, redirectTo, router, trackEvent])

  useEffect(() => {
    clearError()
  }, [clearError])

  useEffect(() => {
    if (resendCooldown <= 0) return
    const timer = setTimeout(() => setResendCooldown((c) => c - 1), 1000)
    return () => clearTimeout(timer)
  }, [resendCooldown])

  const passwordCriteria = useMemo(
    () => ({
      length: password.length >= 8,
      hasUpper: /[A-Z]/.test(password),
      hasNumber: /[0-9]/.test(password),
      hasSpecial: /[^A-Za-z0-9]/.test(password),
    }),
    [password]
  )

  const strengthScore = useMemo(() => {
    let score = 0
    if (passwordCriteria.length) score += 1
    if (passwordCriteria.hasUpper) score += 1
    if (passwordCriteria.hasNumber) score += 1
    if (passwordCriteria.hasSpecial) score += 1
    return score
  }, [passwordCriteria])

  const strengthLabel = useMemo(() => {
    if (password.length === 0) return { text: 'Empty', color: 'bg-gray-200 dark:bg-gray-700' }
    if (strengthScore <= 1) return { text: 'Weak', color: 'bg-red-500' }
    if (strengthScore === 2) return { text: 'Fair', color: 'bg-amber-500' }
    if (strengthScore === 3) return { text: 'Good', color: 'bg-blue-500' }
    return { text: 'Enterprise Strong', color: 'bg-emerald-500' }
  }, [password, strengthScore])

  const passwordsMatch =
    password.length > 0 && confirmPassword.length > 0 && password === confirmPassword
  const passwordsMismatch = confirmPassword.length > 0 && password !== confirmPassword

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    clearError()

    if (!fullName.trim() || !email.trim() || !username.trim() || !password) {
      setFormError('Please fill out all required fields.')
      return
    }

    if (password.length < 8) {
      setFormError('Enterprise security policy requires a password of at least 8 characters.')
      return
    }

    if (password !== confirmPassword) {
      setFormError('Passwords do not match.')
      return
    }

    if (!agreeTerms) {
      setFormError('Please acknowledge the Master Services Agreement & Privacy Policy.')
      return
    }

    setIsSubmitting(true)
    const result = await register({
      email,
      password,
      fullName,
      username,
      companyName: companyName || 'Giantech Empire',
      redirectTo: redirectTo || undefined,
      signupSource: redirectTo ? 'desktop-handoff' : 'auth-portal',
    })
    setIsSubmitting(false)

    if (result.success) {
      if (result.requiresEmailVerification) {
        setRegisteredEmail(email.trim())
        setVerificationRequired(true)
        setResendCooldown(30)
      }
    }
  }

  const handleResendVerification = async () => {
    if (!registeredEmail || resendCooldown > 0 || resending) return
    setResending(true)
    setResendMessage(null)
    const res = await resendVerification(registeredEmail, redirectTo || undefined)
    setResending(false)

    if (res.success) {
      setResendMessage('Confirmation link re-dispatched from auth@tchuekam.com via Resend.')
      setResendCooldown(30)
    } else {
      setResendMessage(res.error || 'Could not resend email right now. Try again shortly.')
    }
  }

  const loginHref = redirectTo
    ? `/login?redirect_to=${encodeURIComponent(redirectTo)}`
    : '/login'

  if (verificationRequired) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-slate-100 flex items-center justify-center p-4">
        <div className="w-full max-w-lg bg-slate-900/90 border border-slate-800 rounded-2xl p-8 shadow-2xl backdrop-blur-xl text-center space-y-6">
          <div className="w-16 h-16 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl flex items-center justify-center mx-auto text-emerald-400">
            <Mail className="w-8 h-8 animate-pulse" />
          </div>

          <div className="space-y-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Verify your enterprise email
            </h1>
            <p className="text-sm text-slate-400">
              We dispatched an activation link from{' '}
              <span className="text-slate-200 font-medium">auth@tchuekam.com</span> to:
            </p>
            <p className="font-semibold text-emerald-400 bg-emerald-500/10 py-1.5 px-4 rounded-lg inline-block border border-emerald-500/20">
              {registeredEmail}
            </p>
          </div>

          <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4 text-xs text-slate-300 text-left space-y-2">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
              <span>Click the verification button in your email to activate your workspace.</span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
              <span>
                Row-Level Security, user profile, and tracking telemetry are already provisioned.
              </span>
            </div>
          </div>

          {resendMessage && (
            <div className="text-xs text-indigo-300 bg-indigo-500/10 border border-indigo-500/30 rounded-xl p-3">
              {resendMessage}
            </div>
          )}

          <div className="flex flex-col sm:flex-row gap-3 pt-1">
            <a
              href="https://mail.google.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm transition"
            >
              Open Gmail <ExternalLink className="w-4 h-4" />
            </a>
            <button
              type="button"
              onClick={handleResendVerification}
              disabled={resendCooldown > 0 || resending}
              className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium text-sm transition disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
              <span>
                {resending
                  ? 'Sending...'
                  : resendCooldown > 0
                  ? `Resend in ${resendCooldown}s`
                  : 'Resend Email'}
              </span>
            </button>
          </div>

          <div className="border-t border-slate-800 pt-4 text-xs text-slate-400 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setVerificationRequired(false)}
              className="text-slate-400 hover:text-white underline"
            >
              Use different email
            </button>
            <div>
              Already verified?{' '}
              <Link href={loginHref} className="text-indigo-400 hover:text-indigo-300 font-medium">
                Proceed to Sign In
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex">
      {/* LEFT COLUMN: Tchuekam Agent Value Prop & Branding */}
      <div className="hidden lg:flex lg:w-5/12 xl:w-1/2 flex-col justify-between p-12 bg-gradient-to-br from-slate-950 via-indigo-950/70 to-slate-900 border-r border-slate-800/80 relative overflow-hidden">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-10 right-10 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 space-y-6">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-amber-400 p-0.5 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                <span className="text-amber-400 font-bold text-lg select-none">☤</span>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-lg tracking-tight text-white">
                  Tchuekam Agent
                </span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  GIANTECH EMPIRE
                </span>
              </div>
              <p className="text-[11px] text-slate-400">Self-Improving Autonomous AI Architecture</p>
            </div>
          </div>

          <div className="pt-6 space-y-4 max-w-lg">
            <h1 className="text-3xl xl:text-4xl font-extrabold tracking-tight text-white leading-tight">
              The Self-Improving AI Agent & Multi-Model Platform
            </h1>
            <p className="text-slate-400 text-sm leading-relaxed">
              Enterprise access to autonomous closed-loop learning, dynamic skill synthesis, and
              multi-channel orchestration across Telegram, Discord, Slack, and Desktop TUI.
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-3 p-3.5 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-md">
              <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 shrink-0 font-bold">
                ☤
              </div>
              <div>
                <p className="text-xs font-semibold text-white">Autonomous Learning Loop</p>
                <p className="text-[11px] text-slate-400">
                  Creates skills from experience, nudges persistence, and refines dialectic user
                  models.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3.5 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-md">
              <div className="w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shrink-0">
                <Cpu className="w-5 h-5" />
              </div>
              <div>
                <p className="text-xs font-semibold text-white">Universal Multi-Model Orchestration</p>
                <p className="text-[11px] text-slate-400">
                  Zero-lockin routing across Tchuekam Portal, OpenRouter, NVIDIA NIM, and GPU
                  clusters.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3.5 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-md">
              <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
                <Server className="w-5 h-5" />
              </div>
              <div>
                <p className="text-xs font-semibold text-white">Supabase Cloud Cluster: Active</p>
                <p className="text-[11px] text-slate-400">
                  Strict Row-Level Security on PostgreSQL with subagent memory isolation.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="relative z-10 pt-8 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <span className="w-2 h-2 rounded-full bg-emerald-400 -ml-4" />
            <span className="text-slate-400">Cluster: Tchuekam-tech (eu-central-1)</span>
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

      {/* RIGHT COLUMN: Enterprise Sign Up Form */}
      <div className="flex-1 flex flex-col justify-center px-6 sm:px-12 lg:px-16 xl:px-24 py-12 overflow-y-auto">
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
              Create Agent Account
            </h2>
            <p className="text-xs sm:text-sm text-slate-400">
              Provision your autonomous agent workspace and team credentials.
            </p>
          </div>

          <OAuthButtons redirectTo={redirectTo} dividerText="Or register with work email" />

          {(formError || authError) && (
            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-red-400" />
              <div className="flex-1 font-medium">{formError || authError}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Full Name <span className="text-amber-400">*</span>
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="text"
                    required
                    placeholder="Rostand Tchuekam"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Agent Handle <span className="text-amber-400">*</span>
                </label>
                <div className="relative">
                  <AtSign className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="text"
                    required
                    placeholder="tchuekam"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Work Email <span className="text-amber-400">*</span>
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
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Organization / Team Workspace
              </label>
              <div className="relative">
                <Building2 className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                <input
                  type="text"
                  placeholder="Giantech Empire / Lab"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500 transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Master Password <span className="text-amber-400">*</span>
              </label>
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

              {password.length > 0 && (
                <div className="mt-2 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-400">Security Score:</span>
                    <span className="font-semibold text-slate-300">{strengthLabel.text}</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden flex gap-1">
                    <div
                      className={`h-full flex-1 rounded-full ${
                        strengthScore >= 1 ? strengthLabel.color : 'bg-slate-800'
                      }`}
                    />
                    <div
                      className={`h-full flex-1 rounded-full ${
                        strengthScore >= 2 ? strengthLabel.color : 'bg-slate-800'
                      }`}
                    />
                    <div
                      className={`h-full flex-1 rounded-full ${
                        strengthScore >= 3 ? strengthLabel.color : 'bg-slate-800'
                      }`}
                    />
                    <div
                      className={`h-full flex-1 rounded-full ${
                        strengthScore >= 4 ? strengthLabel.color : 'bg-slate-800'
                      }`}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-1 text-[10px] text-slate-400 pt-1">
                    <span
                      className={
                        passwordCriteria.length ? 'text-emerald-400 flex items-center gap-1' : 'flex items-center gap-1'
                      }
                    >
                      {passwordCriteria.length ? '✓' : '•'} 8+ Characters
                    </span>
                    <span
                      className={
                        passwordCriteria.hasUpper ? 'text-emerald-400 flex items-center gap-1' : 'flex items-center gap-1'
                      }
                    >
                      {passwordCriteria.hasUpper ? '✓' : '•'} Uppercase letter
                    </span>
                    <span
                      className={
                        passwordCriteria.hasNumber ? 'text-emerald-400 flex items-center gap-1' : 'flex items-center gap-1'
                      }
                    >
                      {passwordCriteria.hasNumber ? '✓' : '•'} At least 1 number
                    </span>
                    <span
                      className={
                        passwordCriteria.hasSpecial ? 'text-emerald-400 flex items-center gap-1' : 'flex items-center gap-1'
                      }
                    >
                      {passwordCriteria.hasSpecial ? '✓' : '•'} Special character
                    </span>
                  </div>
                </div>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Confirm Password <span className="text-amber-400">*</span>
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  placeholder="••••••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className={`w-full bg-slate-900 border rounded-xl pl-9 pr-10 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 transition ${
                    passwordsMatch
                      ? 'border-emerald-500/60 focus:ring-emerald-500/50'
                      : passwordsMismatch
                      ? 'border-red-500/60 focus:ring-red-500/50'
                      : 'border-slate-800 focus:ring-amber-500/50'
                  }`}
                />
                {passwordsMatch && (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 absolute right-3 top-3" />
                )}
              </div>
              {passwordsMismatch && (
                <p className="text-[11px] text-red-400 mt-1">Passwords do not match.</p>
              )}
            </div>

            <div className="flex items-start gap-2 pt-1">
              <input
                id="terms"
                type="checkbox"
                checked={agreeTerms}
                onChange={(e) => setAgreeTerms(e.target.checked)}
                className="mt-0.5 rounded border-slate-700 bg-slate-900 text-amber-500 focus:ring-amber-400 w-3.5 h-3.5 cursor-pointer"
              />
              <label
                htmlFor="terms"
                className="text-[11px] text-slate-400 cursor-pointer select-none leading-relaxed"
              >
                I agree to the{' '}
                <span className="text-amber-400 hover:underline">Tchuekam Agent Terms</span>,{' '}
                <span className="text-amber-400 hover:underline">Privacy Policy</span>, and{' '}
                <span className="text-amber-400 hover:underline">
                  Autonomous Protocol Safety Guidelines
                </span>
                .
              </label>
            </div>

            <button
              type="submit"
              disabled={isSubmitting || authLoading}
              className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-amber-500 via-indigo-600 to-purple-600 hover:from-amber-400 hover:to-purple-500 text-white font-semibold text-xs tracking-wide shadow-lg shadow-amber-500/20 transition disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {isSubmitting || authLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Provisioning Tchuekam Agent Workspace...</span>
                </>
              ) : (
                <>
                  <span>Create Tchuekam Agent Account</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="text-center text-xs text-slate-400 pt-2 border-t border-slate-800">
            Already registered with an agent workspace?{' '}
            <Link
              href={loginHref}
              className="text-amber-400 hover:text-amber-300 font-semibold underline-offset-4 hover:underline"
            >
              Sign In to Console
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function RegisterPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 text-xs">
          Loading Tchuekam Agent Registration...
        </div>
      }
    >
      <RegisterPageInner />
    </Suspense>
  )
}
