import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin, isAdminUser } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  try {
    const authHeader = req.headers.get('authorization') || ''
    const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : ''

    if (!token) {
      return NextResponse.json(
        { error: 'Missing Authorization token' },
        { status: 401, headers: { 'Cache-Control': 'no-store, private' } }
      )
    }

    const supabaseAdmin = getSupabaseAdmin()
    const { data: callerData, error: callerError } = await supabaseAdmin.auth.getUser(token)

    if (callerError || !callerData?.user) {
      return NextResponse.json(
        { error: 'Invalid or expired session token' },
        { status: 401, headers: { 'Cache-Control': 'no-store, private' } }
      )
    }

    const user = callerData.user
    return NextResponse.json(
      {
        id: user.id,
        email: user.email || '',
        isAdmin: isAdminUser(user),
      },
      { headers: { 'Cache-Control': 'no-store, private' } }
    )
  } catch (err) {
    console.error('[api/me] error:', err)
    return NextResponse.json(
      { error: 'Failed to verify session' },
      { status: 500, headers: { 'Cache-Control': 'no-store, private' } }
    )
  }
}
