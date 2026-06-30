import { atom } from 'nanostores'

import { chatMessageText } from '@/lib/chat-messages'

import { $messages } from './session'

export interface ComparisonRequest {
  /** The assistant response being compared (shown for reference). */
  messageText: string
  /** Id of that assistant message — used to recover the original question. */
  messageId: string
  /** The user prompt that produced the response; re-run against the new model. */
  sourcePrompt?: string
}

export const $comparisonRequest = atom<ComparisonRequest | null>(null)

/** Walk back from the assistant message to the user turn that prompted it. */
function findSourcePrompt(assistantMessageId: string): string | undefined {
  const messages = $messages.get()
  const index = messages.findIndex(message => message.id === assistantMessageId)

  if (index < 0) {
    return undefined
  }

  for (let i = index - 1; i >= 0; i -= 1) {
    const message = messages[i]

    if (message.role === 'user' && !message.hidden) {
      return chatMessageText(message).trim() || undefined
    }
  }

  return undefined
}

export function openComparison(request: ComparisonRequest): void {
  $comparisonRequest.set({
    ...request,
    sourcePrompt: request.sourcePrompt ?? findSourcePrompt(request.messageId)
  })
}

export function closeComparison(): void {
  $comparisonRequest.set(null)
}
