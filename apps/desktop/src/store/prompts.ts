import { atom } from 'nanostores'

export type GatewayPromptRequest =
  | {
      kind: 'approval'
      command: string
      description: string
      patternKeys?: string[]
      sessionId: string
    }
  | {
      kind: 'sudo'
      requestId: string
      sessionId: string | null
    }
  | {
      kind: 'secret'
      requestId: string
      envVar: string
      prompt: string
      sessionId: string | null
    }

export const $gatewayPrompt = atom<GatewayPromptRequest | null>(null)

export function setGatewayPrompt(prompt: GatewayPromptRequest): void {
  $gatewayPrompt.set(prompt)
}

export function clearGatewayPrompt(filter?: { requestId?: string; sessionId?: string | null }): void {
  const current = $gatewayPrompt.get()

  if (!current) {
    return
  }

  if (filter?.requestId) {
    if (current.kind === 'approval' || current.requestId !== filter.requestId) {
      return
    }
  }

  if (filter?.sessionId && current.sessionId && current.sessionId !== filter.sessionId) {
    return
  }

  $gatewayPrompt.set(null)
}
