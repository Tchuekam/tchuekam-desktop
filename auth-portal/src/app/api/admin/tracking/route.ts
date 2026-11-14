import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin, isAdminIdentity } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  try {
    const authHeader = req.headers.get('authorization') || ''
    const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : ''

    if (!token) {
      return NextResponse.json({ error: 'Missing Authorization token' }, { status: 401 })
    }

    const supabaseAdmin = getSupabaseAdmin()
    const { data: callerData, error: callerError } = await supabaseAdmin.auth.getUser(token)

    if (callerError || !callerData?.user) {
      return NextResponse.json({ error: 'Invalid or expired session token' }, { status: 401 })
    }

    const caller = callerData.user
    const { data: callerProfile } = await supabaseAdmin
      .from('profiles')
      .select('role')
      .eq('id', caller.id)
      .maybeSingle()

    if (!isAdminIdentity(caller.email, callerProfile?.role)) {
      return NextResponse.json(
        { error: 'Admin privileges required to access global user tracking' },
        { status: 403 }
      )
    }

    const listAllAuthUsers = async () => {
      const collected: NonNullable<
        Awaited<ReturnType<typeof supabaseAdmin.auth.admin.listUsers>>['data']
      >['users'] = []
      const perPage = 1000
      for (let page = 1; page <= 20; page++) {
        const res = await supabaseAdmin.auth.admin.listUsers({ page, perPage })
        if (res.error) throw res.error
        const batch = res.data?.users || []
        collected.push(...batch)
        if (batch.length < perPage) break
      }
      return collected
    }

    const [profilesRes, eventsRes, authUsers] = await Promise.all([
      supabaseAdmin
        .from('profiles')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(5000),
      supabaseAdmin
        .from('auth_events')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(200),
      listAllAuthUsers(),
    ])

    const profiles = profilesRes.data || []
    const events = eventsRes.data || []

    const profileMap = new Map(profiles.map((p) => [p.id, p]))
    const authUserIds = new Set(authUsers.map((au) => au.id))
    const mergedUsers = authUsers.map((au) => {
      const p = profileMap.get(au.id)
      return {
        id: au.id,
        email: au.email || p?.email || '',
        full_name: p?.full_name || au.user_metadata?.full_name || null,
        username: p?.username || au.user_metadata?.username || null,
        company_name: p?.company_name || au.user_metadata?.company_name || 'Giantech Empire',
        role: p?.role || 'Agent Architect',
        email_confirmed_at: au.email_confirmed_at || p?.email_confirmed_at || null,
        last_sign_in_at: au.last_sign_in_at || p?.last_sign_in_at || null,
        login_count: p?.login_count ?? (au.last_sign_in_at ? 1 : 0),
        signup_source: p?.signup_source || au.user_metadata?.signup_source || 'auth-portal',
        provider: (au.app_metadata?.provider as string) || 'email',
        created_at: au.created_at,
      }
    })
    for (const p of profiles) {
      if (!authUserIds.has(p.id)) {
        mergedUsers.push({
          id: p.id,
          email: p.email || '',
          full_name: p.full_name || null,
          username: p.username || null,
          company_name: p.company_name || 'Giantech Empire',
          role: p.role || 'Agent Architect',
          email_confirmed_at: p.email_confirmed_at || null,
          last_sign_in_at: p.last_sign_in_at || null,
          login_count: p.login_count ?? 0,
          signup_source: p.signup_source || 'auth-portal',
          provider: 'email',
          created_at: p.created_at,
        })
      }
    }

    // Sort newest first
    mergedUsers.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

    const now = Date.now()
    const sevenDaysMs = 7 * 24 * 60 * 60 * 1000
    const twentyFourHoursMs = 24 * 60 * 60 * 1000

    const summary = {
      totalUsers: mergedUsers.length,
      verifiedUsers: mergedUsers.filter((u) => Boolean(u.email_confirmed_at)).length,
      unverifiedUsers: mergedUsers.filter((u) => !u.email_confirmed_at).length,
      totalLogins: mergedUsers.reduce((acc, u) => acc + (u.login_count || 0), 0),
      signupsLast7Days: mergedUsers.filter(
        (u) => now - new Date(u.created_at).getTime() <= sevenDaysMs
      ).length,
      eventsLast24Hours: events.filter(
        (e) => now - new Date(e.created_at).getTime() <= twentyFourHoursMs
      ).length,
    }

    return NextResponse.json({
      summary,
      users: mergedUsers,
      events,
    })
  } catch (err) {
    console.error('[api/admin/tracking] error:', err)
    return NextResponse.json({ error: 'Failed to load tracking telemetry' }, { status: 500 })
  }
}
