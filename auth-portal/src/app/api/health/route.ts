import { NextResponse } from 'next/server'

export async function GET() {
  return NextResponse.json({
    status: 'healthy',
    service: 'tchuekam-auth',
    timestamp: new Date().toISOString(),
  })
}
