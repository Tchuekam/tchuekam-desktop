import { beforeEach, describe, expect, it, vi } from 'vitest'

import { displayModelName, formatModelStatusLabel } from '@/lib/model-status-label'

const {
  mockApi,
  mockGetConnection
} = vi.hoisted(() => ({
  mockApi: vi.fn(),
  mockGetConnection: vi.fn()
}))

Object.defineProperty(globalThis, 'window', {
  configurable: true,
  value: {
    hermesDesktop: {
      api: mockApi,
      getConnection: mockGetConnection
    },
    location: { href: 'http://127.0.0.1:18789/' }
  },
  writable: true
})

import { buildVoiceWsUrl } from '@/hermes'
import {
  $activeMbowaRoute,
  $intelligenceStatus,
  applyIntelligenceRouteEvent,
  refreshIntelligenceStatus,
  switchIntelligenceMode
} from '@/store/intelligence'
import type { IntelligenceStatusResponse } from '@/types/hermes'

function makeStatus(overrides: Partial<IntelligenceStatusResponse> = {}): IntelligenceStatusResponse {
  return {
    active_tier: 'cloud',
    connectivity: 'online',
    consecutive_failures: 0,
    degraded: false,
    last_checked_at: 100,
    last_error: '',
    last_provider: 'gemini',
    local_runtime: {
      active_port: null,
      active_role: null,
      active_served_model: null,
      active_weights: null,
      binary_path: 'C:/hermes/llama-server.exe',
      download: null,
      hardware: {
        cpu_count: 4,
        gpu_layers: 0,
        ram_gb: 8,
        recommended_ctx_size: 4096,
        recommended_threads: 3
      },
      installed_ggufs: ['Qwen3-0.6B-Q4_K_M.gguf'],
      models: [],
      ollama_models: [],
      ready: true,
      running: false
    },
    mode: 'hybrid',
    offline: false,
    online: true,
    voice: {
      duplex_ws_path: '/api/ws/voice',
      kokoro_ready: true,
      whisper_local_ready: true
    },
    ...overrides
  }
}

describe('MbowaGPT formatting and Intelligence store', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockGetConnection.mockReset()
    $intelligenceStatus.set(null)
    $activeMbowaRoute.set(null)
  })

  it('formats MbowaGPT specialist model identifiers cleanly', () => {
    expect(displayModelName('mbowagpt')).toBe('MbowaGPT')
    expect(displayModelName('mbowagpt-auto')).toBe('MbowaGPT Auto')
    expect(displayModelName('mbowagpt-cybertrunk')).toBe('MbowaGPT Cybertrunk')
    expect(displayModelName('mbowagpt-relentless')).toBe('MbowaGPT Relentless')
    expect(formatModelStatusLabel('mbowagpt-cybertrunk', { reasoningEffort: 'none' })).toContain('MbowaGPT Cybertrunk')
  })

  it('refreshes and switches intelligence modes via backend API and updates nanostores', async () => {
    mockApi
      .mockResolvedValueOnce(makeStatus({ connectivity: 'offline', offline: true, online: false, active_tier: 'local' }))
      .mockResolvedValueOnce(makeStatus({ mode: 'local', active_tier: 'local' }))

    const refreshed = await refreshIntelligenceStatus(true)
    expect(refreshed?.offline).toBe(true)
    expect($intelligenceStatus.get()?.active_tier).toBe('local')

    const switched = await switchIntelligenceMode('local')
    expect(switched?.mode).toBe('local')
    expect(mockApi).toHaveBeenLastCalledWith({
      body: { mode: 'local', persist: true },
      method: 'POST',
      path: '/api/intelligence/mode'
    })
  })

  it('applies specialist route events cleanly onto nanostore', () => {
    $intelligenceStatus.set(makeStatus())
    applyIntelligenceRouteEvent({
      display_name: 'MbowaGPT Cybertrunk',
      model: 'mbowagpt-cybertrunk',
      offline: true,
      provider: 'mbowagpt',
      specialist_key: 'cybertrunk',
      tier: 'local'
    })

    expect($activeMbowaRoute.get()?.display_name).toBe('MbowaGPT Cybertrunk')
    expect($intelligenceStatus.get()?.offline).toBe(true)
    expect($intelligenceStatus.get()?.active_tier).toBe('local')
  })

  it('builds /api/ws/voice URL with session_id preserving auth query', async () => {
    mockGetConnection.mockResolvedValue({
      token: 'tok-123',
      url: 'http://127.0.0.1:18789',
      wsUrl: 'ws://127.0.0.1:18789/api/ws?token=tok-123'
    })

    const url = await buildVoiceWsUrl('sess-42')
    expect(url).toBe('ws://127.0.0.1:18789/api/ws/voice?token=tok-123&session_id=sess-42')
  })
})
