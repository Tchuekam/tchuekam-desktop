import { afterEach, describe, expect, it } from 'vitest'

import {
  $activeAssistant,
  $pendingSessionConfig,
  clearPendingSession,
  consumePendingSession,
  peekPendingSession,
  queuePendingSession,
  setActiveAssistant
} from './pending-session'

afterEach(() => {
  $pendingSessionConfig.set(null)
  $activeAssistant.set(null)
})

describe('pending-session store', () => {
  it('queues and peeks without consuming', () => {
    queuePendingSession({ kind: 'comparison', prompt: 'hello', model: 'gpt-4o', provider: 'openai' })

    expect(peekPendingSession()).toMatchObject({ kind: 'comparison', prompt: 'hello' })
    // Peek must not clear — createBackendSessionForSend still needs it.
    expect($pendingSessionConfig.get()).not.toBeNull()
  })

  it('consume returns the config exactly once', () => {
    queuePendingSession({ kind: 'image', prompt: 'a cat' })

    expect(consumePendingSession()).toMatchObject({ kind: 'image', prompt: 'a cat' })
    expect(consumePendingSession()).toBeNull()
    expect($pendingSessionConfig.get()).toBeNull()
  })

  it('clear is a no-op when already empty (no spurious set)', () => {
    let writes = 0
    const off = $pendingSessionConfig.listen(() => {
      writes += 1
    })

    clearPendingSession()
    expect(writes).toBe(0)

    queuePendingSession({ kind: 'prompt', prompt: 'x' })
    clearPendingSession()
    expect(writes).toBe(2) // one queue, one clear
    off()
  })

  it('tracks the active assistant for attribution', () => {
    const assistant = { id: 'a1', name: 'Legal', icon: '⚖️', color: 'blue' }
    setActiveAssistant(assistant)

    expect($activeAssistant.get()).toEqual(assistant)

    setActiveAssistant(null)
    expect($activeAssistant.get()).toBeNull()
  })
})
