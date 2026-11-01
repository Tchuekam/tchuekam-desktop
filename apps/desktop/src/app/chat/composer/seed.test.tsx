import { AssistantRuntimeProvider, type ThreadMessage, useExternalStoreRuntime } from '@assistant-ui/react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { $pendingComposerSeed, queueComposerSeed } from '@/store/composer'

import type { ChatBarState } from './types'

import { ChatBar } from './index'

const state: ChatBarState = {
  model: { model: 'test-model', provider: 'test', canSwitch: false },
  tools: { enabled: false, label: '' },
  voice: { enabled: false, active: false }
}

interface HarnessProps {
  acceptsSeed: boolean
  disabled: boolean
  onSubmit: () => boolean
}

function Harness({ acceptsSeed, disabled, onSubmit }: HarnessProps) {
  const runtime = useExternalStoreRuntime<ThreadMessage>({
    messages: [],
    isRunning: false,
    onNew: async () => {}
  })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatBar
        acceptsSeed={acceptsSeed}
        busy={false}
        disabled={disabled}
        onCancel={() => {}}
        onSubmit={onSubmit}
        state={state}
      />
    </AssistantRuntimeProvider>
  )
}

function composerText() {
  return screen.getByRole('textbox', { name: 'Message' }).textContent ?? ''
}

beforeAll(() => {
  // jsdom has neither API; the composer reads both on mount.
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  )
  vi.stubGlobal(
    'matchMedia',
    (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false
    })
  )
})

beforeEach(() => {
  $pendingComposerSeed.set(null)
})

afterEach(() => {
  cleanup()
  $pendingComposerSeed.set(null)
})

describe('ChatBar seed handoff', () => {
  it('appends a queued seed once the composer is enabled, and never submits it', () => {
    const onSubmit = vi.fn(() => true)

    queueComposerSeed('Draft a CV')
    render(<Harness acceptsSeed disabled={false} onSubmit={onSubmit} />)

    expect(composerText()).toContain('Draft a CV')
    expect($pendingComposerSeed.get()).toBeNull()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('keeps the seed while the composer is disabled, then delivers it on enable', () => {
    const onSubmit = vi.fn(() => true)

    queueComposerSeed('Draft a CV')
    const { rerender } = render(<Harness acceptsSeed disabled onSubmit={onSubmit} />)

    expect(composerText()).toBe('')
    expect($pendingComposerSeed.get()).toBe('Draft a CV')

    rerender(<Harness acceptsSeed disabled={false} onSubmit={onSubmit} />)

    expect(composerText()).toContain('Draft a CV')
    expect($pendingComposerSeed.get()).toBeNull()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('does not append the text twice when the composer is disabled and re-enabled', () => {
    const onSubmit = vi.fn(() => true)

    queueComposerSeed('Draft a CV')
    const { rerender } = render(<Harness acceptsSeed disabled={false} onSubmit={onSubmit} />)
    rerender(<Harness acceptsSeed disabled onSubmit={onSubmit} />)
    rerender(<Harness acceptsSeed disabled={false} onSubmit={onSubmit} />)

    expect(composerText().match(/Draft a CV/g)).toHaveLength(1)
  })

  it('leaves the seed for the new-chat composer when this composer is not a new chat', () => {
    queueComposerSeed('Draft a CV')
    render(<Harness acceptsSeed={false} disabled={false} onSubmit={() => true} />)

    expect(composerText()).toBe('')
    expect($pendingComposerSeed.get()).toBe('Draft a CV')
  })
})
