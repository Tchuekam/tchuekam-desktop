import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabaseAdmin'
import { checkRateLimit, getClientIp } from '@/lib/rateLimit'

const ALLOWED_EVENTS = new Set([
  'magic_link_sent',
  'verification_resent',
  'password_reset_requested',
  'password_updated',
  'logout',
  'desktop_handoff',
])

const AUTH_REQUIRED_EVENTS = new Set([
  'password_updated',
  'logout',
  'desktop_handoff',
])

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function sanitizeMetadata(raw: unknown): Record<string, unknown> {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return {}
  }
  const serialized = JSON.stringify(raw)
  if (serialized.length > 2048) {
    return { truncated: true }
  }
  return raw as Record<string, unknown>
}

export async function POST(req: NextRequest) {
  try {
    const ipAddress = getClientIp(req)
    const rl = checkRateLimit(`track:${ipAddress}`, 60, 60_000)
    if (!rl.allowed) {
      return NextResponse.json(
        { ok: false, error: 'Rate limit exceeded' },
        { status: 429 }
      )
    }

    const body = await req.json().catch(() => ({}))
    const eventType = typeof body?.event_type === 'string' ? body.event_type.trim() : ''

    if (!ALLOWED_EVENTS.has(eventType)) {
      return NextResponse.json({ ok: false, error: 'Invalid event type' }, { status: 400 })
    }

    const supabaseAdmin = getSupabaseAdmin()
    const authHeader = req.headers.get('authorization') || ''
    const bearerToken = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : ''

    let userId: string | null = null
    let email: string = typeof body?.email === 'string' ? body.email.trim().toLowerCase() : ''

    if (bearerToken) {
      const { data: userRes, error: authErr } = await supabaseAdmin.auth.getUser(bearerToken)
      if (authErr || !userRes?.user) {
        return NextResponse.json(
          { ok: false, error: 'Invalid or expired authorization token' },
          { status: 401 }
        )
      }
      userId = userRes.user.id
      email = (userRes.user.email || email).toLowerCase()
    }

    if (AUTH_REQUIRED_EVENTS.has(eventType) && !userId) {
      return NextResponse.json(
        { ok: false, error: 'Authentication required for this event type' },
        { status: 401 }
      )
    }

    if (email && (email.length > 254 || !EMAIL_RE.test(email))) {
      return NextResponse.json(
        { ok: false, error: 'Invalid email address format' },
        { status: 400 }
      )
    }

    if (!userId && email) {
      const { data: profileMatch } = await supabaseAdmin
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
      if (profileMatch?.id) {
        userId = profileMatch.id
      }
    }

    if (!email) {
      return NextResponse.json(
        { ok: false, error: 'Email is required to log this auth event' },
        { status: 400 }
      )
    }

    const userAgent = (req.headers.get('user-agent') || '').slice(0, 300)
    const provider =
      typeof body?.provider === 'string' ? body.provider.trim().slice(0, 64) || 'email' : 'email'
    const source =
      typeof body?.source === 'string'
        ? body.source.trim().slice(0, 64) || 'auth-portal'
        : 'auth-portal'
    const metadata = sanitizeMetadata(body?.metadata)

    const { error: insertError } = await supabaseAdmin.from('auth_events').insert({
      user_id: userId,
      email,
      event_type: eventType,
      provider,
      ip_address: ipAddress,
      user_agent: userAgent,
      source,
      metadata,
    })

    if (insertError) {
      console.error('[api/track] insert error:', insertError.message)
      return NextResponse.json(
        { ok: false, error: 'Failed to record event' },
        { status: 500 }
      )
    }

    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[api/track] unexpected error:', err)
    return NextResponse.json({ ok: false, error: 'Failed to record event' }, { status: 500 })
  }
}
