import { type ReactNode, useEffect } from 'react'

import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { triggerHaptic } from '@/lib/haptics'
import { cn } from '@/lib/utils'

interface OverlayViewProps {
  children: ReactNode
  onClose: () => void
  closeLabel?: string
  contentClassName?: string
  headerContent?: ReactNode
  rootClassName?: string
}

export function OverlayView({
  children,
  onClose,
  closeLabel = 'Close',
  contentClassName,
  headerContent,
  rootClassName
}: OverlayViewProps) {
  const closeOverlay = () => {
    triggerHaptic('close')
    onClose()
  }

  // Esc dismisses every OverlayView-based overlay. Nested Radix dialogs
  // stop propagation themselves, so opening (e.g.) the model picker inside
  // Settings still closes the picker first instead of the underlying overlay.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) {
        return
      }

      event.preventDefault()
      triggerHaptic('close')
      onClose()
    }

    window.addEventListener('keydown', onKeyDown)

    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-[80] bg-black/22 p-2 backdrop-blur-[0.125rem] sm:p-6"
      onClick={event => {
        if (event.target === event.currentTarget) {
          closeOverlay()
        }
      }}
      role="presentation"
    >
      <div
        className={cn(
          'relative flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-(--ui-stroke-secondary) bg-(--ui-chat-surface-background) shadow-md',
          rootClassName
        )}
      >
        <div className="pointer-events-none flex items-center gap-2 border-b border-(--ui-stroke-tertiary)/70 px-2.5 py-2 sm:absolute sm:inset-x-0 sm:top-0 sm:z-10 sm:block sm:h-[calc(var(--titlebar-height)+0.1875rem)] sm:border-b-0 sm:p-0 [-webkit-app-region:drag]">
          {headerContent && (
            <div className="pointer-events-auto min-w-0 flex-1 sm:absolute sm:left-1/2 sm:top-[calc(1rem+var(--titlebar-height)/2)] sm:flex-none sm:-translate-x-1/2 sm:-translate-y-1/2 [-webkit-app-region:no-drag]">
              {headerContent}
            </div>
          )}

          <Button
            aria-label={closeLabel}
            className="pointer-events-auto ml-auto h-7 w-7 shrink-0 rounded-md text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground sm:absolute sm:right-3 sm:top-[calc(0.1875rem+var(--titlebar-height)/2)] sm:ml-0 sm:-translate-y-1/2 [-webkit-app-region:no-drag]"
            onClick={closeOverlay}
            size="icon"
            variant="ghost"
          >
            <Codicon name="close" size="1rem" />
          </Button>
        </div>

        <div className={cn('min-h-0 flex flex-1 flex-col pt-(--titlebar-height)', contentClassName)}>{children}</div>
      </div>
    </div>
  )
}
