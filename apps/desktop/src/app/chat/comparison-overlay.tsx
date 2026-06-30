import { useStore } from '@nanostores/react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle
} from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { closeComparison, $comparisonRequest } from '@/store/model-comparison'
import { $currentModel, $currentProvider } from '@/store/session'

import { NEW_CHAT_ROUTE } from '../routes'

const COMPARISON_MODELS = [
  { label: 'Claude Opus 4.8', model: 'claude-opus-4-8', provider: 'anthropic' },
  { label: 'Claude Sonnet 4.6', model: 'claude-sonnet-4-6', provider: 'anthropic' },
  { label: 'Claude Haiku 4.5', model: 'claude-haiku-4-5-20251001', provider: 'anthropic' },
  { label: 'GPT-4o', model: 'gpt-4o', provider: 'openai' },
  { label: 'GPT-4o mini', model: 'gpt-4o-mini', provider: 'openai' },
  { label: 'Gemini 2.0 Flash', model: 'gemini-2.0-flash', provider: 'google' },
  { label: 'Gemini 1.5 Pro', model: 'gemini-1.5-pro', provider: 'google' },
  { label: 'Llama 3.3 70B', model: 'llama-3.3-70b-versatile', provider: 'groq' }
] as const

export function ComparisonOverlay() {
  const navigate = useNavigate()
  const request = useStore($comparisonRequest)
  const currentModel = useStore($currentModel)
  const currentProvider = useStore($currentProvider)

  const [selectedModel, setSelectedModel] = useState<(typeof COMPARISON_MODELS)[number] | null>(null)

  function handleRunComparison() {
    if (!selectedModel || !request) return

    try {
      window.sessionStorage.setItem(
        'tchuekam.pending-comparison',
        JSON.stringify({
          prompt: `[Comparison mode — model: ${selectedModel.label}]\n\nPlease answer the following as if you were providing an alternative perspective:\n\n${request.messageText}`,
          comparisonModel: selectedModel.model,
          comparisonProvider: selectedModel.provider
        })
      )
    } catch {
      // Best-effort
    }

    closeComparison()
    navigate(NEW_CHAT_ROUTE)
  }

  const isCurrentModel = (m: (typeof COMPARISON_MODELS)[number]) =>
    m.model === currentModel && m.provider === currentProvider

  return (
    <Sheet onOpenChange={open => !open && closeComparison()} open={!!request}>
      <SheetContent className="flex w-full max-w-5xl flex-col gap-0 p-0 sm:max-w-5xl" side="right">
        <SheetHeader className="shrink-0 border-b border-(--ui-stroke-tertiary) px-6 py-4">
          <SheetTitle className="flex items-center gap-2 text-base">
            <Codicon name="diff" size="1rem" />
            Compare with another model
          </SheetTitle>
          <p className="text-xs text-muted-foreground">
            Select a model to run the same response through. The comparison opens in a new session.
          </p>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* Left — original response */}
          <div className="flex min-h-0 w-1/2 flex-col border-r border-(--ui-stroke-tertiary)">
            <div className="flex h-9 shrink-0 items-center gap-2 border-b border-(--ui-stroke-quaternary) bg-(--ui-bg-quinary) px-4">
              <span className="text-[0.7rem] font-semibold uppercase tracking-[0.1em] text-(--ui-text-tertiary)">
                Original
              </span>
              {currentModel && (
                <span className="rounded-md bg-(--ui-bg-tertiary) px-1.5 py-0.5 font-mono text-[0.65rem] text-(--ui-text-secondary)">
                  {currentModel}
                </span>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {request && (
                <pre className="whitespace-pre-wrap break-words font-sans text-[0.875rem] leading-relaxed text-foreground">
                  {request.messageText}
                </pre>
              )}
            </div>
          </div>

          {/* Right — model picker */}
          <div className="flex min-h-0 w-1/2 flex-col">
            <div className="flex h-9 shrink-0 items-center gap-2 border-b border-(--ui-stroke-quaternary) bg-(--ui-bg-quinary) px-4">
              <span className="text-[0.7rem] font-semibold uppercase tracking-[0.1em] text-(--ui-text-tertiary)">
                Compare with
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="space-y-1.5">
                {COMPARISON_MODELS.map(m => {
                  const isCurrent = isCurrentModel(m)
                  const isSelected = selectedModel?.model === m.model

                  return (
                    <button
                      className={cn(
                        'w-full rounded-lg border px-3 py-2.5 text-left transition-colors',
                        isSelected
                          ? 'border-blue-500/60 bg-blue-500/10'
                          : isCurrent
                            ? 'cursor-default border-(--ui-stroke-tertiary) opacity-40'
                            : 'border-(--ui-stroke-tertiary) hover:border-(--ui-stroke-secondary) hover:bg-(--ui-control-hover-background)'
                      )}
                      disabled={isCurrent}
                      key={m.model}
                      onClick={() => setSelectedModel(m)}
                      type="button"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className={cn('text-sm font-medium', isSelected ? 'text-blue-600 dark:text-blue-400' : 'text-foreground')}>
                          {m.label}
                        </span>
                        <div className="flex items-center gap-1.5">
                          {isCurrent && (
                            <span className="rounded-full bg-(--ui-bg-tertiary) px-1.5 py-0.5 text-[0.62rem] text-(--ui-text-tertiary)">
                              Current
                            </span>
                          )}
                          {isSelected && (
                            <Codicon className="text-blue-500" name="check" size="0.875rem" />
                          )}
                        </div>
                      </div>
                      <span className="text-[0.7rem] text-(--ui-text-tertiary)">{m.provider}</span>
                    </button>
                  )
                })}
              </div>

              <p className="mt-4 text-xs text-muted-foreground">
                The comparison will open in a new session. Make sure the selected model's provider is configured in Settings → Keys.
              </p>
            </div>

            <div className="shrink-0 border-t border-(--ui-stroke-tertiary) p-4">
              <Button
                className="w-full gap-2"
                disabled={!selectedModel}
                onClick={handleRunComparison}
                type="button"
              >
                <Codicon name="play" size="0.875rem" />
                Run comparison
                {selectedModel && <span className="opacity-70">· {selectedModel.label}</span>}
              </Button>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
