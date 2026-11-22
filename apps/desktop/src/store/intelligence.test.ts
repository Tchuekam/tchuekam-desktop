import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  $activeMbowaRoute,
  $intelligenceStatus,
  applyIntelligenceRouteEvent,
  refreshIntelligenceStatus,
  switchIntelligenceMode
} from '@/store/intelligence'
import type { IntelligenceStatusResponse } from '@/types/hermes'

const mockStatus: IntelligenceStatusResponse = {
  active_tier: 'local',
  autonomy: {
    active_plan: {
      completed_steps: 2,
      failed_steps: 0,
      objective: 'Executive Business Intelligence Report',
      plan_id: 'plan_1234',
      status: 'completed',
      total_steps: 2,
      verified: true
    },
    identity: {
      creator: 'Tchuekam Loic Rostand (Giantech Empire)',
      name: 'TchuekaM',
      title: 'TchuekaM Autonomous Agentic Operating System',
      uptime_seconds: 120
    },
    self_conscious: true,
    skills_ecosystem: {
      all_domains_ready: true,
      domains: [],
      domains_covered: 8,
      domains_total: 8,
      total_skills: 170
    },
    tool_health: {
      available_toolsets_count: 20,
      circuit_open_tools: [],
      fallbacks_used: 1,
      success_rate: 100,
      total_calls: 12,
      total_registered: 45,
      total_successes: 12,
      unavailable_toolsets_count: 0
    },
    verified_deliverables_count: 2
  },
  connectivity: 'offline',
  consecutive_failures: 0,
  degraded: false,
  last_checked_at: Date.now(),
  last_error: '',
  last_provider: 'mbowagpt',
  local_runtime: {
    active_port: 8791,
    active_role: 'mbowagpt-relentless',
    active_served_model: 'mbowagpt-relentless',
    active_weights: 'Qwen2.5-0.5B-Instruct-Q4_K_M.gguf',
    binary_path: 'llama-server.exe',
    hardware: {
      cpu_count: 4,
      gpu_layers: 0,
      ram_gb: 8,
      recommended_ctx_size: 4096,
      recommended_threads: 4
    },
    installed_ggufs: ['Qwen2.5-0.5B-Instruct-Q4_K_M.gguf'],
    models: [],
    ollama_models: [],
    ready: true,
    running: true
  },
  mode: 'hybrid',
  offline: true,
  online: false,
  voice: {
    duplex_ws_path: '/api/ws/voice',
    kokoro_ready: true,
    whisper_local_ready: true
  }
}

vi.mock('@/hermes', () => ({
  getIntelligenceStatus: vi.fn(async () => mockStatus),
  installLocalIntelligenceModel: vi.fn(async () => ({ model_id: 'mbowagpt', ok: true })),
  preloadLocalIntelligence: vi.fn(async () => ({ model_id: 'mbowagpt', ok: true, served_model: 'mbowagpt' })),
  setIntelligenceMode: vi.fn(async (mode: string) => ({ ...mockStatus, mode }))
}))

describe('intelligence and autonomous engine store', () => {
  beforeEach(() => {
    $intelligenceStatus.set(null)
    $activeMbowaRoute.set(null)
  })

  it('loads intelligence and self-conscious autonomy status from backend', async () => {
    const res = await refreshIntelligenceStatus(false)

    expect(res?.autonomy?.self_conscious).toBe(true)
    expect(res?.autonomy?.identity.name).toBe('TchuekaM')
    expect(res?.autonomy?.skills_ecosystem.domains_covered).toBe(8)
    expect(res?.autonomy?.tool_health.success_rate).toBe(100)
    expect($intelligenceStatus.get()?.autonomy?.active_plan?.verified).toBe(true)
  })

  it('switches intelligence mode and updates specialist route state', async () => {
    const updated = await switchIntelligenceMode('local')

    expect(updated?.mode).toBe('local')

    applyIntelligenceRouteEvent({
      display_name: 'MbowaGPT Relentless',
      model: 'mbowagpt-relentless',
      offline: true,
      provider: 'mbowagpt',
      specialist_key: 'relentless',
      tier: 'local'
    })

    expect($activeMbowaRoute.get()?.display_name).toBe('MbowaGPT Relentless')
    expect($intelligenceStatus.get()?.active_tier).toBe('local')
  })
})
