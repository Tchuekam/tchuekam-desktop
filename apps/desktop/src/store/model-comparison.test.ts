import { afterEach, describe, expect, it } from 'vitest'

import type { ChatMessage } from '@/lib/chat-messages'

import { $comparisonRequest, closeComparison, openComparison } from './model-comparison'
import { $messages } from './session'

function msg(id: string, role: ChatMessage['role'], text: string, hidden = false): ChatMessage {
  return { id, role, parts: [{ type: 'text', text }], hidden }
}

afterEach(() => {
  $comparisonRequest.set(null)
  $messages.set([])
})

describe('openComparison source-prompt recovery', () => {
  it('walks back to the user turn that produced the response', () => {
    $messages.set([
      msg('u1', 'user', 'What is the capital of France?'),
      msg('a1', 'assistant', 'Paris.')
    ])

    openComparison({ messageId: 'a1', messageText: 'Paris.' })

    expect($comparisonRequest.get()?.sourcePrompt).toBe('What is the capital of France?')
  })

  it('skips hidden user messages when recovering the prompt', () => {
    $messages.set([
      msg('u1', 'user', 'real question'),
      msg('u-hidden', 'user', 'injected context', true),
      msg('a1', 'assistant', 'answer')
    ])

    openComparison({ messageId: 'a1', messageText: 'answer' })

    expect($comparisonRequest.get()?.sourcePrompt).toBe('real question')
  })

  it('leaves sourcePrompt undefined when no preceding user turn exists', () => {
    $messages.set([msg('a1', 'assistant', 'orphan answer')])

    openComparison({ messageId: 'a1', messageText: 'orphan answer' })

    expect($comparisonRequest.get()?.sourcePrompt).toBeUndefined()
  })

  it('respects an explicitly provided sourcePrompt', () => {
    $messages.set([msg('u1', 'user', 'ignored'), msg('a1', 'assistant', 'answer')])

    openComparison({ messageId: 'a1', messageText: 'answer', sourcePrompt: 'explicit' })

    expect($comparisonRequest.get()?.sourcePrompt).toBe('explicit')
  })

  it('closeComparison resets the request', () => {
    openComparison({ messageId: 'x', messageText: 'y' })
    closeComparison()

    expect($comparisonRequest.get()).toBeNull()
  })
})
