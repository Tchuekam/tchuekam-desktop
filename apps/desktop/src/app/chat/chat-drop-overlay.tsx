import { Codicon } from '@/components/ui/codicon'
import { cn } from '@/lib/utils'

/**
 * Full-bleed affordance shown while files are dragged over the chat area. Always
 * `pointer-events-none` so the drop lands on the real element underneath and the
 * drop-zone handler claims it — the overlay is purely visual. Mirrors the
 * composer surface so the two read as one family.
 */
export function ChatDropOverlay({ active }: { active: boolean }) {
  return (
    <div
      aria-hidden
      className={cn(
        'pointer-events-none absolute inset-0 z-40 flex items-center justify-center p-4 transition-opacity duration-150 ease-out',
        active ? 'opacity-100' : 'opacity-0'
      )}
      data-slot="chat-drop-overlay"
    >
      <div className="absolute inset-3 rounded-2xl border-2 border-dashed border-(--tk-indigo-border) bg-[color-mix(in_srgb,var(--tk-indigo-soft)_60%,var(--tk-glass-bg))] backdrop-blur-sm [-webkit-backdrop-filter:blur(8px)]" />
      <div className="tk-glass-elevated relative flex items-center gap-2.5 rounded-full border-(--tk-indigo-border) px-4 py-2 text-[0.8125rem] font-medium text-foreground">
        <Codicon className="text-(--tk-indigo-text)" name="cloud-upload" size="1rem" />
        Drop files to attach
      </div>
    </div>
  )
}
