import { createClient, type SupabaseClient, type User } from '@supabase/supabase-js'

let _adminClient: SupabaseClient | null = null

export function getSupabaseAdmin(): SupabaseClient {
  if (_adminClient) return _adminClient

  const supabaseUrl = (
    process.env.SUPABASE_URL ||
    process.env.NEXT_PUBLIC_SUPABASE_URL ||
    ''
  ).trim()
  const serviceRoleKey = (process.env.SUPABASE_SERVICE_ROLE_KEY || '').trim()

  if (!supabaseUrl || !serviceRoleKey) {
    throw new Error(
      'SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL) and SUPABASE_SERVICE_ROLE_KEY must be configured on the server.'
    )
  }

  _adminClient = createClient(supabaseUrl, serviceRoleKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  })
  return _adminClient
}

export function getAdminEmailSet(): Set<string> {
  const raw = process.env.ADMIN_EMAILS || ''
  return new Set(
    raw
      .split(',')
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean)
  )
}

export function isAdminUser(user?: User | null): boolean {
  if (!user || !user.email_confirmed_at) return false
  const appRole = String(user.app_metadata?.role || '').trim().toLowerCase()
  if (appRole === 'admin') return true
  if (user.email && getAdminEmailSet().has(user.email.trim().toLowerCase())) {
    return true
  }
  return false
}
