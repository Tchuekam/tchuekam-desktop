import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabaseAdmin'

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

export async function POST(req: NextRequest) {
  try {
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
      const { data: userRes } = await supabaseAdmin.auth.getUser(bearerToken)
      if (userRes?.user) {
        userId = userRes.user.id
        email = (userRes.user.email || email).toLowerCase()
      }
    }

    if (AUTH_REQUIRED_EVENTS.has(eventType) && !userId) {
      return NextResponse.json(
        { ok: false, error: 'Authentication required for this event type' },
        { status: 401 }
      )
    }

    if (!userId && email) {
      const { data: profileMatch } = await supabaseAdmin
        .from('profiles')
        .select('id')
        .ilike('email', email)
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

    const forwardedFor = req.headers.get('x-forwarded-for') || ''
    const ipAddress =
      forwardedFor.split(',')[0]?.trim() ||
      req.headers.get('x-real-ip') ||
      'local'
    const userAgent = (req.headers.get('user-agent') || '').slice(0, 300)

    const { error: insertError } = await supabaseAdmin.from('auth_events').insert({
      user_id: userId,
      email,
      event_type: eventType,
      provider: typeof body?.provider === 'string' ? body.provider : 'email',
      ip_address: ipAddress,
      user_agent: userAgent,
      source: typeof body?.source === 'string' ? body.source : 'auth-portal',
      metadata: typeof body?.metadata === 'object' && body.metadata !== null ? body.metadata : {},
    })

    if (insertError) {
      console.error('[api/track] insert error:', insertError.message)
      return NextResponse.json({ ok: false, error: insertError.message }, { status: 500 })
    }

    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('[api/track] unexpected error:', err)
    return NextResponse.json({ ok: false }, { status: 500 })
  }
}
