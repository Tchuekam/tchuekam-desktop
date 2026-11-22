import type { NextRequest } from 'next/server'

const MAX_TRACKED_KEYS = 10_000
const buckets = new Map<string, number[]>()

function sweepStale(cutoff: number): void {
  for (const [k, timestamps] of buckets.entries()) {
    const active = timestamps.filter((t) => t > cutoff)
    if (active.length === 0) {
      buckets.delete(k)
    } else {
      buckets.set(k, active)
    }
  }
}

export function checkRateLimit(
  key: string,
  maxRequests: number,
  windowMs: number
): { allowed: boolean; remaining: number } {
  const now = Date.now()
  const cutoff = now - windowMs

  if (!buckets.has(key) && buckets.size >= MAX_TRACKED_KEYS) {
    sweepStale(cutoff)
    if (buckets.size >= MAX_TRACKED_KEYS) {
      return { allowed: false, remaining: 0 }
    }
  }

  const timestamps = (buckets.get(key) || []).filter((ts) => ts > cutoff)
  if (timestamps.length >= maxRequests) {
    buckets.set(key, timestamps)
    return { allowed: false, remaining: 0 }
  }

  timestamps.push(now)
  buckets.set(key, timestamps)
  return { allowed: true, remaining: Math.max(0, maxRequests - timestamps.length) }
}

const VALID_IP_RE = /^[0-9a-fA-F:.]{3,45}$/

export function getClientIp(req: NextRequest): string {
  const xff = req.headers.get('x-forwarded-for') || ''
  const firstXff = xff.split(',')[0]?.trim()
  if (firstXff && VALID_IP_RE.test(firstXff)) {
    return firstXff
  }
  const realIp = (req.headers.get('x-real-ip') || '').trim()
  if (realIp && VALID_IP_RE.test(realIp)) {
    return realIp
  }
  return 'unknown'
}
