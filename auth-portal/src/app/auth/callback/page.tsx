'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import type { EmailOtpType } from '@supabase/supabase-js'
import { supabase } from '../../../lib/supabase'
import { resolvePostAuthDestination } from '../../../lib/redirect'
import { CheckCircle2, AlertCircle, RefreshCw, ArrowRight } from 'lucide-react'

function AuthCallbackInner() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying')
  const [message, setMessage] = useState('Validating cryptographic session token...')

  useEffect(() => {
    let active = true

    const completeAuth = async () => {
      try {
        const rawHash =
          typeof window !== 'undefined' && window.location.hash.startsWith('#')
            ? window.location.hash.slice(1)
            : ''
        const hashParams = new URLSearchParams(rawHash)

        const errorParam =
          searchParams.get('error_description') ||
          searchParams.get('error') ||
          hashParams.get('error_description') ||
          hashParams.get('error')
        if (errorParam) {
          if (!active) return
          setStatus('error')
          setMessage(decodeURIComponent(errorParam.replace(/\+/g, ' ')))
          return
        }

        const code = searchParams.get('code')
        const tokenHash = searchParams.get('token_hash')
        const typeParam = searchParams.get('type') || hashParams.get('type')
        const nextParam = searchParams.get('next') || searchParams.get('redirect_to')

        let observedRecovery = typeParam === 'recovery' || nextParam === '/reset-password'

        // 1. Exchange PKCE code if provided and session not already hydrated by detectSessionInUrl
        const {
          data: { session: existingSession },
        } = await supabase.auth.getSession()

        let activeSession = existingSession

        if (!activeSession && code) {
          const { data, error } = await supabase.auth.exchangeCodeForSession(code)
          if (error) {
            // Re-check session in case auto-detection completed concurrently
            const { data: retryData } = await supabase.auth.getSession()
            if (!retryData.session) {
              throw error
            }
            activeSession = retryData.session
          } else {
            activeSession = data.session
          }
        } else if (!activeSession && tokenHash && typeParam) {
          const { data, error } = await supabase.auth.verifyOtp({
            token_hash: tokenHash,
            type: typeParam as EmailOtpType,
          })
          if (error) throw error
          activeSession = data.session
        } else if (!activeSession) {
          // Wait cleanly for detectSessionInUrl / hash fragment hydration
          activeSession = await new Promise((resolve) => {
            let settled = false
            const { data: sub } = supabase.auth.onAuthStateChange((event, sess) => {
              if (event === 'PASSWORD_RECOVERY') {
                observedRecovery = true
              }
              if (!settled && sess) {
                settled = true
                clearTimeout(timer)
                sub.subscription.unsubscribe()
                resolve(sess)
              }
            })
            const timer = setTimeout(async () => {
              if (settled) return
              settled = true
              sub.subscription.unsubscribe()
              const { data: fallbackData } = await supabase.auth.getSession()
              resolve(fallbackData.session)
            }, 1500)
          })
        }

        if (!active) return

        const isRecovery = observedRecovery
        if (isRecovery) {
          setStatus('success')
          setMessage('Identity verified. Redirecting to password reset...')
          setTimeout(() => router.replace('/reset-password'), 600)
          return
        }

        if (!activeSession) {
          setStatus('success')
          setMessage('Email verification confirmed! Redirecting you to sign in...')
          setTimeout(() => router.replace('/login?verified=true'), 1200)
          return
        }

        setStatus('success')
        const { url, external } = resolvePostAuthDestination(nextParam, activeSession)
        setMessage(
          external
            ? 'Authenticated cleanly. Launching Tchuekam Agent workspace...'
            : 'Identity verified. Redirecting to your control plane...'
        )

        setTimeout(() => {
          if (external) {
            window.location.assign(url)
          } else {
            router.replace(url)
          }
        }, 700)
      } catch (err) {
        if (!active) return
        setStatus('error')
        setMessage(
          err instanceof Error
            ? err.message
            : 'The verification link has expired or was already used.'
        )
      }
    }

    completeAuth()
    return () => {
      active = false
    }
  }, [router, searchParams])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-slate-900/90 border border-slate-800 rounded-2xl p-8 shadow-2xl text-center space-y-5">
        <div className="flex items-center justify-center gap-2 text-xs font-bold tracking-wider text-amber-400 uppercase">
          <span>☤</span>
          <span>Tchuekam Agent Identity</span>
        </div>

        {status === 'verifying' && (
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center mx-auto text-indigo-400">
              <RefreshCw className="w-6 h-6 animate-spin" />
            </div>
            <h1 className="text-lg font-bold text-white">Completing Authentication</h1>
            <p className="text-xs text-slate-400">{message}</p>
          </div>
        )}

        {status === 'success' && (
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto text-emerald-400">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h1 className="text-lg font-bold text-white">Verification Complete</h1>
            <p className="text-xs text-slate-400">{message}</p>
          </div>
        )}

        {status === 'error' && (
          <div className="space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center mx-auto text-red-400">
              <AlertCircle className="w-6 h-6" />
            </div>
            <h1 className="text-lg font-bold text-white">Verification Failed</h1>
            <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded-xl p-3">
              {message}
            </p>
            <div className="flex flex-col sm:flex-row gap-2 pt-1">
              <Link
                href="/login"
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition"
              >
                Return to Sign In <ArrowRight className="w-3.5 h-3.5" />
              </Link>
              <Link
                href="/register"
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition"
              >
                Create Account
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400 text-xs">
          Initializing callback verification...
        </div>
      }
    >
      <AuthCallbackInner />
    </Suspense>
  )
}
