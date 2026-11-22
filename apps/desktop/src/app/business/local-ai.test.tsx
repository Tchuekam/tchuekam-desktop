// @vitest-environment node
import './test-dom-setup'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type * as ReactRouter from 'react-router-dom'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setTerminalTakeover } from '@/app/right-sidebar/store'
import type { BusinessLocalAiStatus } from '@/global'

import { extractDocumentFromFile, runDocumentAiOperation } from './services/ai-orchestrator'
import { $businessDocuments, createBusinessDocument, openBusinessDocument, resetBusinessHubStoreForTests } from './store'
import {
  $businessLocalAiDrawerOpen,
  $businessLocalAiMessages,
  $businessLocalAiModalOpen,
  $businessLocalAiStatus,
  askBusinessLocalAgent
} from './store/local-ai'
import { testDom } from './test-dom-setup'
import type { CVData } from './types'

import { BusinessView } from './index'

vi.mock('react-router-dom', async importOriginal => ({
  ...(await importOriginal<typeof ReactRouter>()),
  useNavigate: () => vi.fn()
}))

function createMockStatus(overrides?: Partial<BusinessLocalAiStatus>): BusinessLocalAiStatus {
  return {
    activeModelId: 'qwen3-0.6b-q4',
    activeModelName: 'Qwen3 0.6B (2GB FR/EN)',
    baseDir: 'C:\\Users\\test\\AppData\\Local\\hermes\\business-agent',
    config: {
      ctxSize: 1024,
      enabled: true,
      idleUnloadMs: 180_000,
      modelId: 'qwen3-0.6b-q4',
      threads: 0,
      useKvQuant: true
    },
    enabled: true,
    hardware: {
      cpuCount: 2,
      freeRamMb: 900,
      isLowRamPc: true,
      recommendedModelId: 'qwen3-0.6b-q4',
      totalRamMb: 2048
    },
    installProgress: null,
    installed: true,
    installedModels: ['qwen3-0.6b-q4'],
    installing: false,
    lastError: null,
    models: [
      {
        active: true,
        defaultCtxSize: 1024,
        downloadUrl: 'https://example.invalid/qwen3.gguf',
        estimatedRamMb: 480,
        filename: 'Qwen3-0.6B-Q4_K_M.gguf',
        id: 'qwen3-0.6b-q4',
        installed: true,
        languages: 'FR / EN',
        minRamGb: 2,
        name: 'Qwen3 0.6B (2GB FR/EN)',
        reasoningModel: true,
        recommendedForLowRam: true,
        sizeMb: 378,
        summary: 'Recommended for 2 GB RAM office PCs.'
      }
    ],
    running: false,
    runtimeInstalled: true,
    server: {
      memoryMb: 0,
      modelId: null,
      pid: null,
      port: null,
      uptimeMs: 0
    },
    supported: true,
    ...overrides
  }
}

describe('Business Hub Desktop Local AI Agent', () => {
  const originalHermesDesktop = (window as unknown as { hermesDesktop?: unknown }).hermesDesktop

  beforeEach(() => {
    setTerminalTakeover(false)
    resetBusinessHubStoreForTests()
    $businessLocalAiStatus.set(null)
    $businessLocalAiModalOpen.set(false)
    $businessLocalAiDrawerOpen.set(false)
    $businessLocalAiMessages.set([])
  })

  afterEach(() => {
    cleanup()
    ;(window as unknown as { hermesDesktop?: unknown }).hermesDesktop = originalHermesDesktop
  })

  it('prefers the desktop Business Hub local AI bridge for document operations before backend API', async () => {
    const runOperation = vi.fn().mockResolvedValue({
      durationMs: 420,
      modelId: 'qwen3-0.6b-q4',
      ok: true,
      output: 'Architecte systèmes avec 8 ans d’expérience [to confirm].',
      tokensPerSec: 32.4
    })

    const api = vi.fn()

    ;(window as unknown as { hermesDesktop: Partial<Window['hermesDesktop']> }).hermesDesktop = {
      api: api as unknown as Window['hermesDesktop']['api'],
      businessAi: {
        askAssistant: vi.fn(),
        cancelInstall: vi.fn(),
        deleteModel: vi.fn(),
        getStatus: vi.fn().mockResolvedValue(createMockStatus()),
        install: vi.fn(),
        onStatus: () => () => undefined,
        runOcr: vi.fn(),
        runOperation,
        setConfig: vi.fn(),
        start: vi.fn(),
        unload: vi.fn()
      }
    }

    const res = await runDocumentAiOperation({
      context: 'Principal Systems Architect',
      input: '8 ans architecture systèmes',
      language: 'fr',
      operation: 'improve_summary'
    })

    expect(runOperation).toHaveBeenCalledTimes(1)
    expect(api).not.toHaveBeenCalled()
    expect(res.grounded).toBe(true)
    expect(res.output).toContain('Architecte systèmes')
  })

  it('uses offline RapidOCR bridge for raster image scans in desktop Business Hub', async () => {
    const runOcr = vi.fn().mockResolvedValue({
      engine: 'rapidocr',
      ok: true,
      text: 'FACTURE INV-2026-099 — 250 000 FCFA'
    })

    ;(window as unknown as { hermesDesktop: Partial<Window['hermesDesktop']> }).hermesDesktop = {
      businessAi: {
        askAssistant: vi.fn(),
        cancelInstall: vi.fn(),
        deleteModel: vi.fn(),
        getStatus: vi.fn().mockResolvedValue(createMockStatus()),
        install: vi.fn(),
        onStatus: () => () => undefined,
        runOcr,
        runOperation: vi.fn(),
        setConfig: vi.fn(),
        start: vi.fn(),
        unload: vi.fn()
      }
    }

    const fakePng = new testDom.window.File([new Uint8Array([137, 80, 78, 71])], 'receipt.png', {
      type: 'image/png'
    })

    const extracted = await extractDocumentFromFile(fakePng)

    expect(runOcr).toHaveBeenCalledTimes(1)
    expect(extracted.extractedText).toBe('FACTURE INV-2026-099 — 250 000 FCFA')
  })

  it('opens the Local AI modal, installs the 2GB model, and applies Local Agent output in DocumentWorkspace', async () => {
    const mockInstalledStatus = createMockStatus({ installed: true, running: true, server: { memoryMb: 440, modelId: 'qwen3-0.6b-q4', pid: 1234, port: 54321, uptimeMs: 1200 } })
    const mockUninstalledStatus = createMockStatus({ installed: false, installedModels: [], models: createMockStatus().models.map(m => ({ ...m, installed: false })) })

    const install = vi.fn().mockResolvedValue(mockInstalledStatus)

    const askAssistant = vi.fn().mockResolvedValue({
      durationMs: 650,
      modelId: 'qwen3-0.6b-q4',
      modelName: 'Qwen3 0.6B (2GB FR/EN)',
      ok: true,
      output: 'Executive summary focused on Douala operations [to confirm].',
      tokensPerSec: 28.5
    })

    ;(window as unknown as { hermesDesktop: Partial<Window['hermesDesktop']> }).hermesDesktop = {
      businessAi: {
        askAssistant,
        cancelInstall: vi.fn(),
        deleteModel: vi.fn(),
        getStatus: vi.fn().mockResolvedValue(mockUninstalledStatus),
        install,
        onStatus: () => () => undefined,
        runOcr: vi.fn(),
        runOperation: vi.fn(),
        setConfig: vi.fn(),
        start: vi.fn(),
        unload: vi.fn()
      }
    }

    render(
      <MemoryRouter>
        <BusinessView />
      </MemoryRouter>
    )

    // Open Local AI Settings modal from badge
    const badge = await screen.findByLabelText('Business Hub Local AI Settings')
    fireEvent.click(badge)

    expect(screen.getByText('Business Hub Local AI Agent')).toBeDefined()
    expect(screen.getByText('2 GB Office Mode active')).toBeDefined()

    const installBtn = screen.getByRole('button', { name: /Install/i })
    fireEvent.click(installBtn)

    await waitFor(() => {
      expect(install).toHaveBeenCalledWith({ modelId: 'qwen3-0.6b-q4' })
    })

    // Close modal, create a CV, toggle Local Agent drawer, ask, and apply output
    fireEvent.click(screen.getByLabelText('Close Business Hub Local AI modal'))
    const cvDoc = createBusinessDocument('cv')
    openBusinessDocument(cvDoc.id)

    const toggleDrawerBtn = await screen.findByLabelText('Toggle Business Hub Local Agent')
    fireEvent.click(toggleDrawerBtn)

    await askBusinessLocalAgent('Improve my CV summary', cvDoc)

    const applyBtn = await screen.findByText('Apply to Document')
    fireEvent.click(applyBtn)

    const updatedCv = $businessDocuments.get().find(d => d.id === cvDoc.id)?.data as CVData
    expect(updatedCv.summary).toBe('Executive summary focused on Douala operations [to confirm].')
  })
})
