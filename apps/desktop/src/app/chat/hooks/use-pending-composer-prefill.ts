import { useStore } from '@nanostores/react'
import { useEffect, useRef } from 'react'

import { $pendingSessionConfig } from '@/store/pending-session'

import { requestComposerInsert } from '../composer/focus'

/**
 * Drop a handed-off starter prompt into the composer of a fresh chat.
 *
 * Model Comparison and Image Studio queue a `prompt` on `$pendingSessionConfig`
 * then navigate to the new-chat route. Once the fresh draft is ready (composer
 * mounted + cleared), we inject the prompt via the composer insert bus — the
 * same path drag-drop/terminal-paste use — which also focuses the input. The
 * persona/model half of the handoff is consumed separately at session.create.
 *
 * We never overwrite a prompt the user has already started editing: the insert
 * bus appends, and the applied-key guard keeps the same handoff from firing
 * twice across re-renders.
 */
export function usePendingComposerPrefill(freshDraftReady: boolean): void {
  const pending = useStore($pendingSessionConfig)
  const appliedKeyRef = useRef<string | null>(null)

  useEffect(() => {
    const prompt = pending?.prompt?.trim()

    if (!freshDraftReady || !prompt) {
      return
    }

    const key = `${pending?.kind}:${prompt}`

    if (appliedKeyRef.current === key) {
      return
    }

    appliedKeyRef.current = key
    requestComposerInsert(prompt, { mode: 'block', target: 'main' })
  }, [freshDraftReady, pending])
}
