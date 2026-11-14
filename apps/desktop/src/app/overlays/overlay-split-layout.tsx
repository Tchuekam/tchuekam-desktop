import type { ReactNode } from 'react'

import type { IconComponent } from '@/lib/icons'
import { cn } from '@/lib/utils'

interface OverlaySplitLayoutProps {
  children: ReactNode
  className?: string
}

interface OverlaySidebarProps {
  children: ReactNode
  className?: string
}

interface OverlayMainProps {
  children: ReactNode
  className?: string
}

interface OverlayNavItemProps {
  active: boolean
  icon: IconComponent
  label: string
  onClick: () => void
  trailing?: ReactNode
}

export function OverlaySplitLayout({ children, className }: OverlaySplitLayoutProps) {
  return (
    <div
      className={cn(
        'grid h-full min-h-0 flex-1 grid-cols-[13rem_minmax(0,1fr)] overflow-hidden bg-transparent max-[47.5rem]:grid-cols-1 max-[47.5rem]:grid-rows-[auto_minmax(0,1fr)]',
        className
      )}
    >
      {children}
    </div>
  )
}

export function OverlaySidebar({ children, className }: OverlaySidebarProps) {
  return (
    <aside
      className={cn(
        'flex min-h-0 flex-col gap-0.5 overflow-y-auto bg-(--ui-sidebar-surface-background) px-2.5 py-3 max-[47.5rem]:flex-row max-[47.5rem]:items-center max-[47.5rem]:gap-1 max-[47.5rem]:overflow-x-auto max-[47.5rem]:overflow-y-hidden max-[47.5rem]:border-b max-[47.5rem]:border-(--ui-stroke-tertiary) max-[47.5rem]:px-2 max-[47.5rem]:py-2',
        className
      )}
    >
      {children}
    </aside>
  )
}

export function OverlayMain({ children, className }: OverlayMainProps) {
  return (
    <main className={cn('flex min-h-0 flex-1 flex-col overflow-hidden bg-transparent p-3', className)}>{children}</main>
  )
}

export function OverlayNavItem({ active, icon: Icon, label, onClick, trailing }: OverlayNavItemProps) {
  return (
    <button
      className={cn(
        'flex h-7 w-full items-center justify-start gap-2 rounded-md border px-2 text-left text-[length:var(--conversation-text-font-size)] font-normal transition-colors max-[47.5rem]:w-auto max-[47.5rem]:shrink-0',
        active
          ? 'border-(--ui-stroke-tertiary) bg-(--ui-bg-tertiary) text-foreground'
          : 'border-transparent bg-transparent text-(--ui-text-secondary) hover:bg-(--chrome-action-hover) hover:text-foreground'
      )}
      onClick={onClick}
      type="button"
    >
      <Icon className={cn('size-4 shrink-0', active ? 'text-foreground/80' : 'text-muted-foreground/80')} />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {trailing}
    </button>
  )
}
