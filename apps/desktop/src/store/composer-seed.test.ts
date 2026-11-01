import { beforeEach, describe, expect, it } from 'vitest'

import { $pendingComposerSeed, clearComposerSeed, queueComposerSeed, takeComposerSeed } from './composer'

beforeEach(() => {
  $pendingComposerSeed.set(null)
})

describe('composer seed', () => {
  it('hands the queued text to the first taker, trimmed, and only once', () => {
    queueComposerSeed('  Draft a CV  ')

    expect(takeComposerSeed()).toBe('Draft a CV')
    expect(takeComposerSeed()).toBeNull()
  })

  it('ignores blank text and keeps a seed that is already queued', () => {
    queueComposerSeed('Draft a CV')
    queueComposerSeed('   ')

    expect(takeComposerSeed()).toBe('Draft a CV')
  })

  it('replaces a seed that has not been taken yet', () => {
    queueComposerSeed('Draft a CV')
    queueComposerSeed('Draft an invoice')

    expect(takeComposerSeed()).toBe('Draft an invoice')
  })

  it('drops a pending seed when clearing', () => {
    queueComposerSeed('Draft a CV')
    clearComposerSeed()

    expect(takeComposerSeed()).toBeNull()
  })
})
