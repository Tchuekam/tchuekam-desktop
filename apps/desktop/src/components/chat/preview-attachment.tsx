import { useStore } from '@nanostores/react'
import { useEffect, useRef, useState } from 'react'

import { MonitorPlay } from '@/lib/icons'
import { normalizeOrLocalPreviewTarget } from '@/lib/local-preview'
import { previewName } from '@/lib/preview-targets'
import { notifyError } from '@/store/notifications'
import {
  $previewTarget,
  dismissPreviewTarget,
  type PreviewRecordSource,
  setCurrentSessionPreviewTarget
} from '@/store/preview'
import { $currentCwd } from '@/store/session'

export function PreviewAttachment({ source = 'manual', target }: { source?: PreviewRecordSource; target: string }) {
  const cwd = useStore($currentCwd)
  const activePreview = useStore($previewTarget)
  const [opening, setOpening] = useState(false)
  const activePreviewRef = useRef(activePreview)
  const cwdRef = useRef(cwd)
  const mountedRef = useRef(false)
  const requestTokenRef = useRef(0)
  const targetRef = useRef(target)
  const name = previewName(target)
  const isActive = activePreview?.source === target

  activePreviewRef.current = activePreview
  cwdRef.current = cwd
  targetRef.current = target

  useEffect(() => {
    mountedRef.current = true

    return () => {
      mountedRef.current = false
      requestTokenRef.current += 1
    }
  }, [])

  useEffect(() => {
    requestTokenRef.current += 1
    setOpening(false)
  }, [cwd, target])

  async function togglePreview() {
    if (opening) {
      return
    }

    if (isActive) {
      dismissPreviewTarget()

      return
    }

    const requestToken = ++requestTokenRef.current
    const requestTarget = target
    const requestCwd = cwd

    setOpening(true)

    try {
      const preview = await normalizeOrLocalPreviewTarget(requestTarget, requestCwd || undefined)

      if (
        !mountedRef.current ||
        requestTokenRef.current !== requestToken ||
        targetRef.current !== requestTarget ||
        cwdRef.current !== requestCwd
      ) {
        return
      }

      if (!preview) {
        throw new Error(`Could not open preview target: ${requestTarget}`)
      }

      const currentPreview = activePreviewRef.current

      if (currentPreview?.source === preview.source && currentPreview.url === preview.url) {
        return
      }

      setCurrentSessionPreviewTarget(preview, source, requestTarget)
    } catch (error) {
      if (
        !mountedRef.current ||
        requestTokenRef.current !== requestToken ||
        targetRef.current !== requestTarget ||
        cwdRef.current !== requestCwd
      ) {
        return
      }

      notifyError(error, 'Preview unavailable')
    } finally {
      if (mountedRef.current && requestTokenRef.current === requestToken) {
        setOpening(false)
      }
    }
  }

  return (
    <div className="tk-glass-subtle tk-surface-hover flex w-full max-w-160 flex-wrap items-center gap-3 rounded-xl px-3 py-2 text-sm hover:border-(--tk-indigo-border)">
      <span
        className={
          isActive
            ? 'grid size-8 shrink-0 place-items-center rounded-lg bg-(--tk-indigo-soft) text-(--tk-indigo-text)'
            : 'grid size-8 shrink-0 place-items-center rounded-lg bg-(--ui-bg-tertiary) text-muted-foreground'
        }
      >
        <MonitorPlay className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[0.8125rem] font-medium leading-[1.2rem] text-foreground/92">{name}</div>
        <div className="truncate font-mono text-[0.6875rem] leading-4 text-muted-foreground/75">{target}</div>
      </div>
      <button
        className="ml-auto shrink-0 rounded-lg border border-(--tk-glass-border) bg-background/60 px-2.5 py-1 text-[0.7rem] font-semibold text-(--ui-text-secondary) transition-colors hover:border-(--tk-indigo-border) hover:bg-(--tk-indigo-soft) hover:text-(--tk-indigo-text) disabled:opacity-50 max-[28rem]:ml-10 max-[28rem]:w-[calc(100%-2.5rem)]"
        disabled={opening}
        onClick={() => void togglePreview()}
        type="button"
      >
        {opening ? 'Opening…' : isActive ? 'Hide' : 'Open preview'}
      </button>
    </div>
  )
}
