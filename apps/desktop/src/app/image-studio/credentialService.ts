import { setEnvVar, deleteEnvVar, revealEnvVar } from '@/hermes'
// @ts-expect-error JS/JSX module without TypeScript declaration file
import { getUserBalance } from './open-generative-ai/packages/studio/src/muapi.js'

export type StudioProviderId = 'fal' | 'muapi'

let memoryKeys: Record<StudioProviderId, string | null> = {
  fal: null,
  muapi: null,
}

let activeProvider: StudioProviderId = 'fal'

export function _resetMemoryKeyForTesting(): void {
  memoryKeys = { fal: null, muapi: null }
  activeProvider = 'fal'
}

export function getActiveStudioProvider(): StudioProviderId {
  if (typeof window !== 'undefined') {
    try {
      const stored = window.localStorage.getItem('tchuekam_studio_provider') as StudioProviderId | null
      if (stored === 'fal' || stored === 'muapi') {
        activeProvider = stored
      }
    } catch {
      // Storage unavailable
    }
  }
  return activeProvider
}

export function setActiveStudioProvider(provider: StudioProviderId): void {
  activeProvider = provider
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem('tchuekam_studio_provider', provider)
      window.dispatchEvent(new CustomEvent('tchuekam:provider-changed', { detail: { provider } }))
    } catch {
      // Storage unavailable
    }
  }
}

export type ValidationResult =
  | { ok: true; balance: number | null; provider?: StudioProviderId }
  | { ok: false; status: number; error: string; provider?: StudioProviderId }

/**
 * Migration & cleanup helper to ensure no plaintext keys remain in localStorage or cookies.
 */
function cleanupLegacyStorage(): string | null {
  if (typeof window === 'undefined') return null

  let migratedKey: string | null = null
  try {
    const legacy = window.localStorage.getItem('muapi_key')
    if (legacy) {
      window.localStorage.removeItem('muapi_key')
      if (legacy !== 'genimage_free_key' && legacy.trim().length > 0) {
        migratedKey = legacy.trim()
      }
    }
  } catch {
    // Ignore storage exceptions
  }

  try {
    document.cookie = 'muapi_key=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax'
    document.cookie = 'fal_key=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax'
  } catch {
    // Ignore cookie exceptions
  }

  return migratedKey
}

/**
 * Retrieve credentials for a specific provider (fal or muapi).
 */
export async function getProviderKey(provider: StudioProviderId): Promise<string | null> {
  if (memoryKeys[provider]) {
    return memoryKeys[provider]
  }

  const isMuapi = provider === 'muapi'
  const secretKey = isMuapi ? 'muapi_key' : 'fal_key'
  const envKey = isMuapi ? 'MUAPI_KEY' : 'FAL_KEY'

  // 1. One-time legacy cleanup for muapi
  if (isMuapi) {
    const legacyMigrated = cleanupLegacyStorage()
    if (legacyMigrated) {
      await saveProviderKey('muapi', legacyMigrated)
      return legacyMigrated
    }
  }

  // 2. Try Electron safeStorage IPC
  try {
    if (window.hermesDesktop?.getSecureSecret) {
      const secureKey = await window.hermesDesktop.getSecureSecret(secretKey)
      if (secureKey && secureKey.trim().length > 0 && secureKey !== 'genimage_free_key') {
        memoryKeys[provider] = secureKey.trim()
        return memoryKeys[provider]
      }
    }
  } catch {
    // Fallback to backend or memory
  }

  // 3. Try Tchuekam backend .env reveal
  try {
    const revealed = await revealEnvVar(envKey)
    if (revealed?.value && revealed.value.trim().length > 0 && revealed.value !== 'genimage_free_key') {
      const trimmed = revealed.value.trim()
      memoryKeys[provider] = trimmed
      // Mirror to safeStorage if available
      void window.hermesDesktop?.setSecureSecret?.(secretKey, trimmed).catch(() => null)
      return memoryKeys[provider]
    }
  } catch {
    // Backend may not have key or be running in remote mode
  }

  return null
}

/**
 * Save credentials for a specific provider.
 */
export async function saveProviderKey(
  provider: StudioProviderId,
  rawKey: string,
): Promise<{ ok: boolean; error?: string }> {
  const trimmed = rawKey.trim()
  if (!trimmed || trimmed === 'genimage_free_key') {
    return { ok: false, error: 'A valid API key is required.' }
  }

  memoryKeys[provider] = trimmed

  cleanupLegacyStorage()

  const secretKey = provider === 'muapi' ? 'muapi_key' : 'fal_key'
  const envKey = provider === 'muapi' ? 'MUAPI_KEY' : 'FAL_KEY'

  // Persist to Electron safeStorage
  try {
    if (window.hermesDesktop?.setSecureSecret) {
      await window.hermesDesktop.setSecureSecret(secretKey, trimmed)
    }
  } catch {
    // SafeStorage optional in web environments
  }

  // Persist to Tchuekam .env
  try {
    await setEnvVar(envKey, trimmed)
  } catch {
    // Ignore if backend is unavailable
  }

  return { ok: true }
}

/**
 * Delete credentials for a specific provider.
 */
export async function deleteProviderKey(provider: StudioProviderId): Promise<{ ok: boolean }> {
  memoryKeys[provider] = null
  cleanupLegacyStorage()

  const secretKey = provider === 'muapi' ? 'muapi_key' : 'fal_key'
  const envKey = provider === 'muapi' ? 'MUAPI_KEY' : 'FAL_KEY'

  try {
    if (window.hermesDesktop?.deleteSecureSecret) {
      await window.hermesDesktop.deleteSecureSecret(secretKey)
    }
  } catch {
    // Ignore
  }

  try {
    await deleteEnvVar(envKey)
  } catch {
    // Ignore
  }

  return { ok: true }
}

/**
 * Validate a key against the provider.
 */
export async function validateProvider(provider: StudioProviderId, key: string): Promise<ValidationResult> {
  if (!key || key === 'genimage_free_key') {
    return { ok: false, status: 401, error: 'Invalid or missing API key.', provider }
  }

  if (provider === 'fal') {
    // Real probe, performed by the backend (so the key never goes to a third
    // party from the renderer): POST /api/providers/validate {key, value}.
    if (key.length < 8) {
      return { ok: false, status: 401, error: 'The FAL API key format is invalid.', provider }
    }
    try {
      const resp = await window.hermesDesktop.api<{ ok?: boolean; reachable?: boolean; message?: string }>({
        path: '/api/providers/validate',
        method: 'POST',
        body: { key: 'FAL_KEY', value: key }
      })
      if (resp?.ok === true) {
        return { ok: true, balance: null, provider }
      }
      if (resp?.reachable === false) {
        // Could not verify — NOT the same as valid. Surface it as "unavailable".
        return { ok: false, status: 503, error: resp.message || 'Could not reach fal.ai to verify the key.', provider }
      }
      return { ok: false, status: 403, error: resp?.message || 'FAL.ai rejected the provided key.', provider }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : String(err)
      return { ok: false, status: 503, error: `Could not verify the key: ${errorMsg}`, provider }
    }
  }

  // MuAPI validation
  try {
    const data = await getUserBalance(key)
    const balance = typeof data?.balance === 'number' ? data.balance : null
    return { ok: true, balance, provider }
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    if (errorMsg.includes('401') || errorMsg.includes('403') || errorMsg.toLowerCase().includes('not authorized')) {
      return { ok: false, status: 403, error: 'The API key was rejected by MuAPI. Please verify your key.', provider }
    }
    return { ok: false, status: 500, error: errorMsg || 'Unable to connect to MuAPI authentication.', provider }
  }
}

// ---------------------------------------------------------------------------
// Backward-compatible aliases for existing studio call-sites & tests
// ---------------------------------------------------------------------------

/**
 * Backward-compatible getter for the primary studio API key.
 * Checks muapi first for existing test suites, or fal.
 */
export async function getStudioApiKey(provider?: StudioProviderId): Promise<string | null> {
  const p = provider || 'muapi'
  return getProviderKey(p)
}

export async function saveStudioApiKey(rawKey: string, provider?: StudioProviderId): Promise<{ ok: boolean; error?: string }> {
  const p = provider || 'muapi'
  return saveProviderKey(p, rawKey)
}

export async function deleteStudioApiKey(provider?: StudioProviderId): Promise<{ ok: boolean }> {
  const p = provider || 'muapi'
  return deleteProviderKey(p)
}

export async function validateApiKey(key: string, provider?: StudioProviderId): Promise<ValidationResult> {
  const p = provider || 'muapi'
  return validateProvider(p, key)
}
