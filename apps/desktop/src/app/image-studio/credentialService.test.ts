import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  getStudioApiKey,
  saveStudioApiKey,
  deleteStudioApiKey,
  validateApiKey,
  _resetMemoryKeyForTesting,
} from './credentialService'

// Mock the hermes backend functions
vi.mock('@/hermes', () => ({
  setEnvVar: vi.fn().mockResolvedValue({ ok: true }),
  deleteEnvVar: vi.fn().mockResolvedValue({ ok: true }),
  revealEnvVar: vi.fn().mockResolvedValue(null),
}))

// Mock muapi getUserBalance
vi.mock('./open-generative-ai/packages/studio/src/muapi.js', () => ({
  getUserBalance: vi.fn(),
}))

import { revealEnvVar, setEnvVar, deleteEnvVar } from '@/hermes'
// @ts-expect-error JS/JSX module without TypeScript declaration file
import { getUserBalance } from './open-generative-ai/packages/studio/src/muapi.js'

describe('Studio Credential Service (P0.1, P0.2)', () => {
  beforeEach(() => {
    _resetMemoryKeyForTesting()
    vi.clearAllMocks()
    localStorage.clear()
    document.cookie = 'muapi_key=; expires=Thu, 01 Jan 1970 00:00:00 GMT'

    // Mock window.hermesDesktop safeStorage IPC
    window.hermesDesktop = {
      getSecureSecret: vi.fn().mockResolvedValue(null),
      setSecureSecret: vi.fn().mockResolvedValue({ ok: true }),
      deleteSecureSecret: vi.fn().mockResolvedValue({ ok: true }),
    } as any
  })

  describe('First launch without credentials', () => {
    it('returns null when no credentials exist in any storage tier', async () => {
      const key = await getStudioApiKey()
      expect(key).toBeNull()
    })

    it('ignores invalid legacy "genimage_free_key" demo key in localStorage and cookies', async () => {
      localStorage.setItem('muapi_key', 'genimage_free_key')
      document.cookie = 'muapi_key=genimage_free_key'

      const key = await getStudioApiKey()
      expect(key).toBeNull()
      // Plaintext must be purged
      expect(localStorage.getItem('muapi_key')).toBeNull()
    })
  })

  describe('Secure Credential Storage & Migration', () => {
    it('migrates valid legacy key from localStorage to secure storage and deletes plaintext copy', async () => {
      const validKey = 'valid_live_muapi_secret_key_123'
      localStorage.setItem('muapi_key', validKey)

      const key = await getStudioApiKey()
      expect(key).toBe(validKey)

      // Verified: Plaintext removed from localStorage
      expect(localStorage.getItem('muapi_key')).toBeNull()

      // Verified: Saved into Electron safeStorage
      expect(window.hermesDesktop?.setSecureSecret).toHaveBeenCalledWith('muapi_key', validKey)

      // Verified: Saved into backend .env
      expect(setEnvVar).toHaveBeenCalledWith('MUAPI_KEY', validKey)
    })

    it('reads credentials from Electron safeStorage when present', async () => {
      const secureKey = 'encrypted_safe_storage_key_999'
        ; (window.hermesDesktop!.getSecureSecret as any).mockResolvedValueOnce(secureKey)

      const key = await getStudioApiKey()
      expect(key).toBe(secureKey)
      expect(window.hermesDesktop?.getSecureSecret).toHaveBeenCalledWith('muapi_key')
    })

    it('falls back to Tchuekam backend .env when safeStorage is empty', async () => {
      const backendKey = 'backend_env_key_555'
        ; (revealEnvVar as any).mockResolvedValueOnce({ value: backendKey })

      const key = await getStudioApiKey()
      expect(key).toBe(backendKey)
      expect(revealEnvVar).toHaveBeenCalledWith('MUAPI_KEY')
    })
  })

  describe('Saving and Replacing Credentials', () => {
    it('rejects empty, blank, or placeholder keys', async () => {
      const res1 = await saveStudioApiKey('')
      expect(res1.ok).toBe(false)
      expect(res1.error).toContain('valid API key is required')

      const res2 = await saveStudioApiKey('   ')
      expect(res2.ok).toBe(false)

      const res3 = await saveStudioApiKey('genimage_free_key')
      expect(res3.ok).toBe(false)
      expect(res3.error).toContain('valid API key is required')
    })

    it('successfully saves valid key and updates memory, safeStorage, and backend .env', async () => {
      const newKey = 'new_production_key_456'
      const res = await saveStudioApiKey(newKey)
      expect(res.ok).toBe(true)

      expect(window.hermesDesktop?.setSecureSecret).toHaveBeenCalledWith('muapi_key', newKey)
      expect(setEnvVar).toHaveBeenCalledWith('MUAPI_KEY', newKey)

      // Fast retrieval from memory cache
      const cached = await getStudioApiKey()
      expect(cached).toBe(newKey)
    })

    it('supports seamless credential replacement', async () => {
      await saveStudioApiKey('key_version_1')
      expect(await getStudioApiKey()).toBe('key_version_1')

      await saveStudioApiKey('key_version_2')
      expect(await getStudioApiKey()).toBe('key_version_2')
      expect(window.hermesDesktop?.setSecureSecret).toHaveBeenLastCalledWith('muapi_key', 'key_version_2')
    })
  })

  describe('Deleting Credentials', () => {
    it('completely purges credential from memory, safeStorage, backend .env, and local storage', async () => {
      await saveStudioApiKey('key_to_delete')
      expect(await getStudioApiKey()).toBe('key_to_delete')

      const res = await deleteStudioApiKey()
      expect(res.ok).toBe(true)

      expect(window.hermesDesktop?.deleteSecureSecret).toHaveBeenCalledWith('muapi_key')
      expect(deleteEnvVar).toHaveBeenCalledWith('MUAPI_KEY')

      const afterDelete = await getStudioApiKey()
      expect(afterDelete).toBeNull()
    })
  })

  describe('API Key Validation & Error Handling (P0.1, P0.6)', () => {
    it('validates active credentials and extracts user balance', async () => {
      ; (getUserBalance as any).mockResolvedValueOnce({ balance: 42.5 })

      const result = await validateApiKey('valid_test_key')
      expect(result.ok).toBe(true)
      if (result.ok) {
        expect(result.balance).toBe(42.5)
      }
    })

    it('returns 403 on authentication rejection (HTTP 401/403)', async () => {
      ; (getUserBalance as any).mockRejectedValueOnce(new Error('Failed to fetch balance: 401 - Unauthorized'))

      const result = await validateApiKey('invalid_or_expired_key')
      expect(result.ok).toBe(false)
      if (!result.ok) {
        expect(result.status).toBe(403)
        expect(result.error).toContain('rejected by the provider')
      }
    })

    it('returns error when provider network or service is unavailable', async () => {
      ; (getUserBalance as any).mockRejectedValueOnce(new Error('Network error: connection refused'))

      const result = await validateApiKey('some_key')
      expect(result.ok).toBe(false)
      if (!result.ok) {
        expect(result.status).toBe(500)
        expect(result.error).toContain('Network error')
      }
    })
  })
})
