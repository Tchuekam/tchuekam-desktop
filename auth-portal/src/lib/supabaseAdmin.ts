import { createClient, SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl =
  process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://fzoiiusuqvjhwivstbyb.supabase.co'

let _adminClient: SupabaseClient | null = null

export function getSupabaseAdmin(): SupabaseClient {
  if (_adminClient) return _adminClient

  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!serviceRoleKey) {
    throw new Error('SUPABASE_SERVICE_ROLE_KEY is not configured on the server.')
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
  const raw =
    process.env.ADMIN_EMAILS ||
    process.env.NEXT_PUBLIC_ADMIN_EMAILS ||
    'founder@tchuekam.com,tchuekrostand@gmail.com,rebornedbetalpha@gmail.com'
  return new Set(
    raw
      .split(',')
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean)
  )
}

export function isAdminIdentity(email?: string | null, role?: string | null): boolean {
  if (role && role.toLowerCase() === 'admin') return true
  if (email && getAdminEmailSet().has(email.trim().toLowerCase())) return true
  return false
}
