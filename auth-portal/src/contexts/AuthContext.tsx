'use client'

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
  useCallback,
} from 'react'
import { User, Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'

export interface UserProfile {
  id: string
  email: string
  full_name: string | null
  username: string | null
  company_name: string | null
  role: string | null
  avatar_url: string | null
  login_count?: number
  last_sign_in_at?: string | null
  email_confirmed_at?: string | null
  signup_source?: string | null
  created_at: string
  updated_at: string
}

export interface EnabledAuthProviders {
  email: boolean
  google: boolean
  github: boolean
}

export interface SignUpParams {
  email: string
  password: string
  fullName: string
  username: string
  companyName?: string
  redirectTo?: string
  signupSource?: string
}

export interface SignUpResult {
  success: boolean
  requiresEmailVerification: boolean
  user?: User | null
  error?: string | null
}

interface AuthContextType {
  user: User | null
  session: Session | null
  profile: UserProfile | null
  loading: boolean
  error: string | null
  isAdmin: boolean
  enabledProviders: EnabledAuthProviders
  clearError: () => void
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>
  signInWithMagicLink: (
    email: string,
    redirectTo?: string
  ) => Promise<{ success: boolean; error?: string }>
  register: (params: SignUpParams) => Promise<SignUpResult>
  resendVerification: (
    email: string,
    redirectTo?: string
  ) => Promise<{ success: boolean; error?: string }>
  loginWithOAuth: (provider: 'google' | 'github', redirectTo?: string) => Promise<void>
  resetPassword: (email: string) => Promise<{ success: boolean; error?: string }>
  updatePassword: (newPassword: string) => Promise<{ success: boolean; error?: string }>
  logout: () => Promise<void>
  refreshProfile: () => Promise<void>
  trackEvent: (
    eventType: string,
    payload?: { email?: string; provider?: string; source?: string; metadata?: Record<string, unknown> }
  ) => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL || '').trim()
const SUPABASE_ANON_KEY = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '').trim()

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [enabledProviders, setEnabledProviders] = useState<EnabledAuthProviders>({
    email: true,
    google: false,
    github: false,
  })

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const syncAdminStatus = useCallback(async (accessToken?: string | null) => {
    if (!accessToken) {
      setIsAdmin(false)
      return
    }
    try {
      const res = await fetch('/api/me', {
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: 'no-store',
      })
      if (!res.ok) {
        setIsAdmin(false)
        return
      }
      const data = await res.json()
      setIsAdmin(Boolean(data?.isAdmin))
    } catch {
      setIsAdmin(false)
    }
  }, [])

  const trackEvent = useCallback(
    async (
      eventType: string,
      payload?: {
        email?: string
        provider?: string
        source?: string
        metadata?: Record<string, unknown>
      }
    ) => {
      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (session?.access_token) {
          headers.Authorization = `Bearer ${session.access_token}`
        }
        await fetch('/api/track', {
          method: 'POST',
          headers,
          keepalive: true,
          body: JSON.stringify({
            event_type: eventType,
            email: payload?.email || user?.email,
            provider: payload?.provider || 'email',
            source: payload?.source || 'auth-portal',
            metadata: payload?.metadata || {},
          }),
        })
      } catch {
        // Non-blocking telemetry
      }
    },
    [session?.access_token, user?.email]
  )

  const fetchProfile = useCallback(async (userId: string) => {
    try {
      const { data, error: profileErr } = await supabase
        .from('profiles')
        .select('*')
        .eq('id', userId)
        .single()

      if (!profileErr && data) {
        setProfile(data as UserProfile)
      } else {
        const { data: userData } = await supabase
          .from('users')
          .select('*')
          .eq('id', userId)
          .single()
        if (userData) {
          setProfile({
            id: userData.id,
            email: userData.email,
            full_name: userData.full_name || userData.username,
            username: userData.username,
            company_name: userData.company_name || 'Giantech Empire',
            role: 'Agent Architect',
            avatar_url: null,
            created_at: userData.created_at || new Date().toISOString(),
            updated_at: userData.updated_at || new Date().toISOString(),
          })
        }
      }
    } catch (err) {
      console.error('Error fetching user profile:', err)
    }
  }, [])

  useEffect(() => {
    let mounted = true

    // Discover dynamically enabled auth providers so UI never exposes unconfigured SSO buttons
    if (SUPABASE_URL && SUPABASE_ANON_KEY) {
      fetch(`${SUPABASE_URL}/auth/v1/settings`, {
        headers: { apikey: SUPABASE_ANON_KEY },
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((settingsData) => {
          if (!mounted || !settingsData?.external) return
          setEnabledProviders({
            email: settingsData.external.email !== false,
            google: Boolean(settingsData.external.google),
            github: Boolean(settingsData.external.github),
          })
        })
        .catch(() => {
          // Keep conservative default (email enabled)
        })
    }

    supabase.auth.getSession().then(({ data: { session: initialSession } }) => {
      if (!mounted) return
      setSession(initialSession)
      setUser(initialSession?.user ?? null)
      if (initialSession?.user) {
        fetchProfile(initialSession.user.id)
        void syncAdminStatus(initialSession.access_token)
      } else {
        setIsAdmin(false)
      }
      setLoading(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      if (!mounted) return
      setSession(newSession)
      setUser(newSession?.user ?? null)
      if (newSession?.user) {
        await Promise.all([
          fetchProfile(newSession.user.id),
          syncAdminStatus(newSession.access_token),
        ])
      } else {
        setProfile(null)
        setIsAdmin(false)
      }
      setLoading(false)
    })

    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [fetchProfile, syncAdminStatus])

  const buildCallbackUrl = (nextPath?: string) => {
    if (typeof window === 'undefined') return undefined
    const base = `${window.location.origin}/auth/callback`
    if (nextPath) {
      return `${base}?next=${encodeURIComponent(nextPath)}`
    }
    return base
  }

  const login = async (
    email: string,
    password: string
  ): Promise<{ success: boolean; error?: string }> => {
    setLoading(true)
    setError(null)
    try {
      const { data, error: signInError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      })

      if (signInError) {
        setError(signInError.message)
        setLoading(false)
        return { success: false, error: signInError.message }
      }

      setUser(data.user)
      setSession(data.session)
      if (data.user) {
        await Promise.all([
          fetchProfile(data.user.id),
          syncAdminStatus(data.session?.access_token),
        ])
      }
      setLoading(false)
      return { success: true }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred during login'
      setError(message)
      setLoading(false)
      return { success: false, error: message }
    }
  }

  const signInWithMagicLink = async (
    email: string,
    redirectTo?: string
  ): Promise<{ success: boolean; error?: string }> => {
    setError(null)
    try {
      const { error: otpError } = await supabase.auth.signInWithOtp({
        email: email.trim(),
        options: {
          shouldCreateUser: true,
          emailRedirectTo: buildCallbackUrl(redirectTo),
        },
      })
      if (otpError) {
        setError(otpError.message)
        return { success: false, error: otpError.message }
      }
      await trackEvent('magic_link_sent', { email: email.trim() })
      return { success: true }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to send sign-in link'
      setError(message)
      return { success: false, error: message }
    }
  }

  const register = async ({
    email,
    password,
    fullName,
    username,
    companyName = 'Giantech Empire',
    redirectTo,
    signupSource = 'auth-portal',
  }: SignUpParams): Promise<SignUpResult> => {
    setLoading(true)
    setError(null)

    try {
      const { data, error: signUpError } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: {
          emailRedirectTo: buildCallbackUrl(redirectTo),
          data: {
            full_name: fullName.trim(),
            username: username.trim().toLowerCase(),
            company_name: companyName.trim(),
            signup_source: signupSource,
          },
        },
      })

      if (signUpError) {
        setError(signUpError.message)
        setLoading(false)
        return { success: false, requiresEmailVerification: false, error: signUpError.message }
      }

      const createdUser = data.user
      const existingAccountNoSession =
        !data.session &&
        Array.isArray(createdUser?.identities) &&
        createdUser.identities.length === 0

      if (existingAccountNoSession) {
        const msg =
          'An account with this email already exists. Please sign in with your password or request a Magic Link.'
        setError(msg)
        setLoading(false)
        return {
          success: false,
          requiresEmailVerification: false,
          error: msg,
        }
      }

      const requiresEmailVerification = !data.session

      if (createdUser && data.session) {
        setUser(createdUser)
        setSession(data.session)
        await Promise.all([
          fetchProfile(createdUser.id),
          syncAdminStatus(data.session.access_token),
        ])
      }

      setLoading(false)
      return {
        success: true,
        requiresEmailVerification,
        user: createdUser,
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'An unexpected error occurred during registration'
      setError(message)
      setLoading(false)
      return { success: false, requiresEmailVerification: false, error: message }
    }
  }

  const resendVerification = async (
    email: string,
    redirectTo?: string
  ): Promise<{ success: boolean; error?: string }> => {
    try {
      const { error: resendErr } = await supabase.auth.resend({
        type: 'signup',
        email: email.trim(),
        options: {
          emailRedirectTo: buildCallbackUrl(redirectTo),
        },
      })
      if (resendErr) {
        return { success: false, error: resendErr.message }
      }
      await trackEvent('verification_resent', { email: email.trim() })
      return { success: true }
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : 'Failed to resend verification email',
      }
    }
  }

  const loginWithOAuth = async (provider: 'google' | 'github', redirectTo?: string) => {
    setError(null)
    try {
      const { error: oAuthError } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: buildCallbackUrl(redirectTo),
        },
      })
      if (oAuthError) {
        setError(oAuthError.message)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to initiate OAuth login'
      setError(message)
    }
  }

  const resetPassword = async (email: string): Promise<{ success: boolean; error?: string }> => {
    setError(null)
    try {
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: buildCallbackUrl('/reset-password'),
      })
      if (resetError) {
        return { success: false, error: resetError.message }
      }
      await trackEvent('password_reset_requested', { email: email.trim() })
      return { success: true }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to send password reset email'
      return { success: false, error: message }
    }
  }

  const updatePassword = async (
    newPassword: string
  ): Promise<{ success: boolean; error?: string }> => {
    setError(null)
    try {
      const { error: updateErr } = await supabase.auth.updateUser({ password: newPassword })
      if (updateErr) {
        return { success: false, error: updateErr.message }
      }
      await trackEvent('password_updated')
      return { success: true }
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : 'Failed to update password',
      }
    }
  }

  const logout = async () => {
    setLoading(true)
    setError(null)
    try {
      await trackEvent('logout')
      await supabase.auth.signOut()
      setUser(null)
      setSession(null)
      setProfile(null)
      setIsAdmin(false)
    } catch (err) {
      console.error('Error logging out:', err)
    } finally {
      setLoading(false)
    }
  }

  const refreshProfile = async () => {
    if (user?.id) {
      await fetchProfile(user.id)
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        profile,
        loading,
        error,
        isAdmin,
        enabledProviders,
        clearError,
        login,
        signInWithMagicLink,
        register,
        resendVerification,
        loginWithOAuth,
        resetPassword,
        updatePassword,
        logout,
        refreshProfile,
        trackEvent,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
