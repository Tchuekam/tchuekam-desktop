import type * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Quiet section header for sidebar panels ("Projects", "Tasks").
 *
 * Deliberately recessive: a header should let the eye skip to the rows under
 * it, so it sits at the tertiary text step in sentence case with no ornament.
 */
export function SidebarPanelLabel({ children, className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'flex min-w-0 items-center pl-2 text-[0.75rem] font-medium tracking-normal text-(--ui-text-tertiary)',
        className
      )}
      {...props}
    >
      <span className="min-w-0 truncate leading-none">{children}</span>
    </span>
  )
}
