import { atom } from 'nanostores'

/**
 * In-memory handoff for "start a chat preconfigured a certain way".
 *
 * Project Assistants, Model Comparison, and Image Studio all need to open a
 * brand-new chat session that is preloaded with some combination of: a starter
 * prompt, a system persona, and a specific model. The session itself isn't
 * created until the user sends their first message (see
 * `createBackendSessionForSend`), so we stash the intent here and consume it
 * at two points:
 *
 *   1. The composer prefill effect reads `prompt` when the fresh draft is ready.
 *   2. `createBackendSessionForSend` reads `systemPrompt`/`model`/`provider`
 *      to seed the session and switch the model, then clears the config.
 *
 * This replaces an earlier `window.sessionStorage` stub that nothing read —
 * keeping it in a nanostore means it survives the in-app navigation without
 * touching disk and is trivially testable.
 */
export interface PendingSessionConfig {
  /** Where this handoff originated — drives attribution + analytics. */
  kind: 'assistant' | 'comparison' | 'image' | 'prompt'
  /** Text to prefill into the composer of the new chat. */
  prompt?: string
  /** Persona seeded as a `system` message on the new session. */
  systemPrompt?: string
  /** Per-session model override applied via `/model` after creation. */
  model?: string
  provider?: string
  /** Attribution — populated when `kind === 'assistant'`. */
  assistant?: ActiveAssistant
}

export interface ActiveAssistant {
  id: string
  name: string
  icon: string
  /** Tailwind-friendly color token from ASSISTANT_COLORS. */
  color: string
}

/** The next session's preconfiguration, or null for a plain new chat. */
export const $pendingSessionConfig = atom<PendingSessionConfig | null>(null)

/** The assistant persona backing the current chat, shown in the header. */
export const $activeAssistant = atom<ActiveAssistant | null>(null)

export function queuePendingSession(config: PendingSessionConfig): void {
  $pendingSessionConfig.set(config)
}

export function consumePendingSession(): PendingSessionConfig | null {
  const config = $pendingSessionConfig.get()
  $pendingSessionConfig.set(null)

  return config
}

export function peekPendingSession(): PendingSessionConfig | null {
  return $pendingSessionConfig.get()
}

export function clearPendingSession(): void {
  if ($pendingSessionConfig.get() !== null) {
    $pendingSessionConfig.set(null)
  }
}

export function setActiveAssistant(assistant: ActiveAssistant | null): void {
  $activeAssistant.set(assistant)
}
