import * as React from 'react'

import { Codicon, type CodiconProps } from '@/components/ui/codicon'
import { cn } from '@/lib/utils'

/**
 * Rounded-card shell for fenced code (and any equivalent: diffs, raw payloads,
 * etc.) sized for the conversation column. Mirrors the expanded tool-row
 * pattern so code blocks read as the same family of artifact.
 */
function CodeCard({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'tk-glass-subtle min-w-0 max-w-full overflow-hidden rounded-xl border-(--tk-glass-border) text-[length:var(--conversation-tool-font-size)] text-muted-foreground shadow-xs',
        className
      )}
      data-slot="code-card"
      {...props}
    />
  )
}

function CodeCardHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'flex items-center justify-between gap-2 border-b border-(--tk-glass-border) bg-(--ui-bg-tertiary)/45 px-3 py-2',
        className
      )}
      data-slot="code-card-header"
      {...props}
    />
  )
}

function CodeCardTitle({ className, children, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'flex min-w-0 items-center gap-1.5 truncate text-[length:var(--conversation-caption-font-size)] font-medium leading-(--conversation-line-height) text-foreground/85',
        className
      )}
      data-slot="code-card-title"
      {...props}
    >
      {children}
    </span>
  )
}

function CodeCardIcon({ className, ...props }: CodiconProps) {
  return (
    <Codicon
      className={cn('shrink-0 text-[0.875rem] leading-none text-(--tk-indigo-text)', className)}
      data-slot="code-card-icon"
      {...props}
    />
  )
}

function CodeCardSubtitle({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span className={cn('font-normal text-muted-foreground', className)} data-slot="code-card-subtitle" {...props} />
  )
}

function CodeCardBody({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'p-2 font-mono text-[0.78rem] leading-[1.6] text-foreground/92 [&_pre]:m-0 [&_pre]:overflow-x-auto [&_pre]:bg-transparent! [&_pre]:px-2 [&_pre]:py-1.5 [&_pre]:font-mono [&_pre]:leading-[1.6]',
        className
      )}
      data-slot="code-card-body"
      {...props}
    />
  )
}

export { CodeCard, CodeCardBody, CodeCardHeader, CodeCardIcon, CodeCardSubtitle, CodeCardTitle }
