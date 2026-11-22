import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { IS_DESKTOP } from '@/lib/platform'
import { cn } from '@/lib/utils'
import { notify } from '@/store/notifications'

import {
  $businessLocalAiChatBusy,
  $businessLocalAiDrawerOpen,
  $businessLocalAiMessages,
  $businessLocalAiModalOpen,
  $businessLocalAiStatus,
  askBusinessLocalAgent,
  buildDeterministicDocumentAudit,
  cancelBusinessLocalAiInstall,
  clearBusinessLocalAiMessages,
  deleteBusinessLocalAiModel,
  installBusinessLocalAi,
  startBusinessLocalAi,
  subscribeBusinessLocalAiStatus,
  unloadBusinessLocalAi,
  updateBusinessLocalAiConfig
} from '../../store/local-ai'
import type { BusinessDocument } from '../../types'

function formatSpeed(bytesPerSec: number): string {
  if (!bytesPerSec || bytesPerSec <= 0) {
    return ''
  }

  if (bytesPerSec >= 1024 * 1024) {
    return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} MB/s`
  }

  return `${Math.round(bytesPerSec / 1024)} KB/s`
}

export function BusinessLocalAiStatusBadge() {
  const status = useStore($businessLocalAiStatus)

  useEffect(() => {
    if (!IS_DESKTOP) {
      return
    }

    return subscribeBusinessLocalAiStatus()
  }, [])

  if (!IS_DESKTOP) {
    return null
  }

  const isInstalling = Boolean(status?.installing)
  const isRunning = Boolean(status?.running)
  const isInstalled = Boolean(status?.installed)
  const isEnabled = status?.enabled !== false

  const dotClass = isInstalling
    ? 'bg-amber-500 animate-pulse'
    : isRunning
      ? 'bg-(--tk-cyan) shadow-[0_0_8px_var(--tk-cyan-glow)]'
      : isInstalled && isEnabled
        ? 'bg-(--tk-indigo)'
        : 'bg-muted-foreground/50'

  const label = isInstalling
    ? `Installing AI${typeof status?.installProgress?.percent === 'number' ? ` (${status.installProgress.percent}%)` : '...'}`
    : isRunning
      ? `Local AI · ${status?.server.memoryMb ? `${status.server.memoryMb} MB` : 'Active'}`
      : isInstalled
        ? isEnabled
          ? 'Local AI · Ready (0 MB)'
          : 'Local AI · Paused'
        : 'Install Local AI (2GB PC)'

  return (
    <button
      aria-label="Business Hub Local AI Settings"
      className="tk-glass-subtle tk-surface-hover inline-flex h-9 items-center gap-2 rounded-xl px-3 text-xs font-semibold tabular-nums hover:border-(--tk-indigo-border) hover:bg-muted/70"
      onClick={() => $businessLocalAiModalOpen.set(true)}
      type="button"
    >
      <span className={cn('size-2 rounded-full', dotClass)} />
      <Codicon name="chip" size="0.9rem" />
      <span>{label}</span>
    </button>
  )
}

export function BusinessLocalAiModal() {
  const open = useStore($businessLocalAiModalOpen)
  const status = useStore($businessLocalAiStatus)
  const [busyAction, setBusyAction] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !IS_DESKTOP) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        $businessLocalAiModalOpen.set(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open])

  if (!IS_DESKTOP || !open) {
    return null
  }

  const models = status?.models ?? []
  const hardware = status?.hardware
  const progress = status?.installProgress
  const isInstalling = Boolean(status?.installing)

  const handleInstall = async (modelId: string) => {
    setBusyAction(`install:${modelId}`)

    try {
      await installBusinessLocalAi(modelId)
      notify({
        kind: 'success',
        message: 'Local Business Hub AI installed and ready for offline use.',
        title: 'Local AI Ready'
      })
    } catch (err) {
      notify({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Installation failed.',
        title: 'Local AI Install Error'
      })
    } finally {
      setBusyAction(null)
    }
  }

  const handleSwitchModel = async (modelId: string) => {
    setBusyAction(`use:${modelId}`)

    try {
      await updateBusinessLocalAiConfig({ enabled: true, modelId })
      notify({
        kind: 'success',
        message: 'Switched active Business Hub local AI model.',
        title: 'Model Selected'
      })
    } finally {
      setBusyAction(null)
    }
  }

  const handleDeleteModel = async (modelId: string) => {
    setBusyAction(`delete:${modelId}`)

    try {
      await deleteBusinessLocalAiModel(modelId)
      notify({
        kind: 'info',
        message: 'Removed local model file to free disk space.',
        title: 'Model Removed'
      })
    } finally {
      setBusyAction(null)
    }
  }

  const handleWarmup = async () => {
    setBusyAction('start')

    try {
      await startBusinessLocalAi()
      notify({
        kind: 'success',
        message: 'Business Hub Local AI engine is warmed up in memory.',
        title: 'Local AI Active'
      })
    } catch (err) {
      notify({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Could not start local AI engine.',
        title: 'Startup Failed'
      })
    } finally {
      setBusyAction(null)
    }
  }

  const handleUnload = async () => {
    setBusyAction('unload')

    try {
      await unloadBusinessLocalAi()
      notify({
        kind: 'info',
        message: 'Local AI unloaded from RAM (0 MB used).',
        title: 'RAM Freed'
      })
    } finally {
      setBusyAction(null)
    }
  }

  return (
    <div
      aria-label="Business Hub Local AI Agent"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-md sm:p-4"
      onClick={event => {
        if (event.target === event.currentTarget) {
          $businessLocalAiModalOpen.set(false)
        }
      }}
      role="dialog"
    >
      <div className="tk-glass-elevated flex max-h-[90dvh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl text-foreground">
        <div className="flex items-center justify-between gap-3 border-b border-(--tk-glass-border) bg-(--ui-bg-tertiary)/35 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-xl bg-linear-to-br from-(--tk-indigo) to-(--tk-cyan) text-white shadow-xs">
              <Codicon name="chip" size="1.1rem" />
            </div>
            <div>
              <h2 className="text-base font-semibold tracking-tight">Business Hub Local AI Agent</h2>
              <p className="text-xs text-muted-foreground">
                Dedicated offline engine for Business Hub only — optimized for 2 GB RAM office PCs.
              </p>
            </div>
          </div>
          <button
            aria-label="Close Business Hub Local AI modal"
            className="rounded-lg p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
            onClick={() => $businessLocalAiModalOpen.set(false)}
            type="button"
          >
            <Codicon name="close" size="1rem" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {/* Hardware & Runtime Status */}
          <div className="grid grid-cols-1 gap-3 rounded-xl border border-(--tk-glass-border) bg-(--tk-glass-subtle-bg) p-4 sm:grid-cols-3">
            <div>
              <div className="text-[0.65rem] font-semibold uppercase tracking-wider text-muted-foreground">
                PC Hardware
              </div>
              <div className="mt-1 text-xs font-bold tabular-nums">
                {hardware ? `${(hardware.totalRamMb / 1024).toFixed(1)} GB RAM · ${hardware.cpuCount} CPU` : 'Desktop PC'}
              </div>
              <div className="text-[0.6875rem] text-muted-foreground">
                {hardware?.isLowRamPc ? '2 GB Office Mode active' : 'Low-RAM profile enforced'}
              </div>
            </div>

            <div>
              <div className="text-[0.65rem] font-semibold uppercase tracking-wider text-muted-foreground">
                Engine State
              </div>
              <div className="mt-1 text-xs font-bold tabular-nums">
                {status?.running
                  ? `Running (${status.server.memoryMb ?? '~450'} MB RAM)`
                  : status?.installed
                    ? 'Ready (0 MB Idle)'
                    : 'Not Installed'}
              </div>
              <div className="text-[0.6875rem] text-muted-foreground">
                {status?.runtimeInstalled ? 'CPU llama.cpp installed' : 'Auto-installs ~24 MB CPU engine'}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-start gap-2 sm:justify-end">
              {status?.installed && !status.running && (
                <button
                  className="tk-btn-primary inline-flex h-8 items-center gap-1.5 rounded-xl px-3 text-xs font-semibold text-white disabled:opacity-50"
                  disabled={busyAction !== null || isInstalling}
                  onClick={() => void handleWarmup()}
                  type="button"
                >
                  <Codicon name="play" size="0.8rem" />
                  {busyAction === 'start' ? 'Starting...' : 'Wake'}
                </button>
              )}
              {status?.running && (
                <button
                  className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-(--tk-glass-border) bg-background/70 px-3 text-xs font-semibold transition hover:border-amber-500/40 hover:text-amber-600 disabled:opacity-50"
                  disabled={busyAction !== null}
                  onClick={() => void handleUnload()}
                  type="button"
                >
                  <Codicon name="debug-stop" size="0.8rem" />
                  Free RAM
                </button>
              )}
            </div>
          </div>

          {/* Live Download Progress */}
          {isInstalling && progress && (
            <div className="space-y-2 rounded-xl border border-(--tk-cyan-border) bg-(--tk-cyan-soft) p-4">
              <div className="flex items-center justify-between gap-2 text-xs font-semibold">
                <span>{progress.message}</span>
                <span className="tabular-nums">
                  {typeof progress.percent === 'number' ? `${progress.percent}%` : '...'}
                  {progress.speedBps > 0 ? ` · ${formatSpeed(progress.speedBps)}` : ''}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-linear-to-r from-(--tk-indigo) to-(--tk-cyan) transition-all duration-200"
                  style={{ width: `${Math.max(4, progress.percent ?? 12)}%` }}
                />
              </div>
              <div className="flex justify-end">
                <button
                  className="text-[0.6875rem] font-semibold text-destructive hover:underline"
                  onClick={() => void cancelBusinessLocalAiInstall()}
                  type="button"
                >
                  Cancel download
                </button>
              </div>
            </div>
          )}

          {/* Model Presets */}
          <div className="space-y-2.5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
              Dedicated Business Hub Models
            </h3>
            <div className="space-y-2">
              {models.map(model => {
                const tooHeavy = Boolean(hardware?.isLowRamPc && model.minRamGb > 2)

                return (
                  <div
                    className={cn(
                      'flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3.5 transition',
                      model.active
                        ? 'border-(--tk-indigo-border) bg-(--tk-indigo-soft)'
                        : 'border-(--tk-glass-border) bg-(--tk-glass-subtle-bg)'
                    )}
                    key={model.id}
                  >
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-xs font-bold">{model.name}</span>
                        <span className="rounded-md bg-muted px-1.5 py-0.5 text-[0.625rem] font-semibold tabular-nums text-muted-foreground">
                          {model.sizeMb} MB disk · ~{model.estimatedRamMb} MB RAM
                        </span>
                        <span className="rounded-md bg-(--tk-indigo-soft) px-1.5 py-0.5 text-[0.625rem] font-semibold text-(--tk-indigo-text)">
                          {model.languages}
                        </span>
                        {model.recommendedForLowRam && (
                          <span className="rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-[0.625rem] font-semibold text-emerald-700 dark:text-emerald-400">
                            Recommended 2GB PC
                          </span>
                        )}
                        {tooHeavy && (
                          <span className="rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[0.625rem] font-semibold text-amber-700 dark:text-amber-400">
                            4GB+ RAM recommended
                          </span>
                        )}
                      </div>
                      <p className="text-[0.6875rem] text-muted-foreground">{model.summary}</p>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {!model.installed ? (
                        <button
                          className="tk-btn-primary inline-flex h-8 items-center gap-1.5 rounded-xl px-3 text-xs font-semibold text-white disabled:opacity-50"
                          disabled={isInstalling || busyAction !== null}
                          onClick={() => void handleInstall(model.id)}
                          type="button"
                        >
                          <Codicon name="cloud-download" size="0.8rem" />
                          Install
                        </button>
                      ) : model.active ? (
                        <span className="inline-flex h-8 items-center gap-1 rounded-xl bg-emerald-500/15 px-2.5 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                          <Codicon name="check" size="0.8rem" />
                          Active
                        </span>
                      ) : (
                        <button
                          className="inline-flex h-8 items-center gap-1 rounded-xl border border-(--tk-glass-border) bg-card px-2.5 text-xs font-semibold transition hover:border-(--tk-indigo-border)"
                          disabled={busyAction !== null}
                          onClick={() => void handleSwitchModel(model.id)}
                          type="button"
                        >
                          Use Model
                        </button>
                      )}

                      {model.installed && (
                        <button
                          aria-label={`Remove ${model.name}`}
                          className="inline-flex h-8 items-center rounded-xl border border-(--tk-glass-border) px-2 text-xs text-muted-foreground hover:border-destructive/40 hover:text-destructive disabled:opacity-40"
                          disabled={busyAction !== null || isInstalling}
                          onClick={() => void handleDeleteModel(model.id)}
                          title="Delete model file"
                          type="button"
                        >
                          <Codicon name="trash" size="0.8rem" />
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 2GB RAM Performance Tuning */}
          {status && (
            <div className="space-y-3 rounded-xl border border-(--tk-glass-border) bg-(--tk-glass-subtle-bg) p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                2 GB RAM Memory & Speed Tuning
              </h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="flex items-center justify-between gap-2 rounded-xl border border-(--tk-glass-border) bg-card/70 px-3 py-2 text-xs">
                  <span className="font-medium">Use Local AI for Business Hub actions</span>
                  <input
                    checked={status.config.enabled}
                    className="size-4 accent-(--tk-indigo)"
                    onChange={event => void updateBusinessLocalAiConfig({ enabled: event.target.checked })}
                    type="checkbox"
                  />
                </label>

                <label className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-card/70 px-3 py-2 text-xs">
                  <span className="font-medium">Q8 KV cache (saves ~50% cache RAM)</span>
                  <input
                    checked={status.config.useKvQuant}
                    className="size-4 accent-primary"
                    onChange={event => void updateBusinessLocalAiConfig({ useKvQuant: event.target.checked })}
                    type="checkbox"
                  />
                </label>

                <div className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-card/70 px-3 py-2 text-xs">
                  <span className="font-medium">Context window</span>
                  <select
                    aria-label="Local AI Context Window"
                    className="rounded border border-border bg-background px-2 py-1 text-xs"
                    onChange={event => void updateBusinessLocalAiConfig({ ctxSize: Number(event.target.value) })}
                    value={status.config.ctxSize}
                  >
                    <option value={512}>512 (Max Speed / Min RAM)</option>
                    <option value={1024}>1024 (2 GB Balanced)</option>
                    <option value={1536}>1536 (4 GB+ Extended)</option>
                  </select>
                </div>

                <div className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-card/70 px-3 py-2 text-xs">
                  <span className="font-medium">Auto-unload idle RAM</span>
                  <select
                    aria-label="Idle Unload Timer"
                    className="rounded border border-border bg-background px-2 py-1 text-xs"
                    onChange={event =>
                      void updateBusinessLocalAiConfig({ idleUnloadMs: Number(event.target.value) })
                    }
                    value={status.config.idleUnloadMs}
                  >
                    <option value={60000}>1 min (Strict 2 GB)</option>
                    <option value={180000}>3 min (Recommended)</option>
                    <option value={300000}>5 min</option>
                    <option value={0}>Keep loaded</option>
                  </select>
                </div>
              </div>
              <p className="text-[0.6875rem] text-muted-foreground">
                Isolated from your main TchuekaM chat model. Scan-to-text images also run offline via local RapidOCR when available.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function BusinessLocalAiInlineCard() {
  const messages = useStore($businessLocalAiMessages)
  const busy = useStore($businessLocalAiChatBusy)
  const status = useStore($businessLocalAiStatus)

  if (!IS_DESKTOP || (messages.length === 0 && !busy)) {
    return null
  }

  return (
    <div className="mt-3 rounded-2xl border border-primary/25 bg-card/90 p-3.5 shadow-xs backdrop-blur-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Codicon className="text-primary" name="chip" size="0.9rem" />
          <span className="text-xs font-bold">
            Business Hub Local AI {status?.activeModelName ? `· ${status.activeModelName}` : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!status?.installed && (
            <button
              className="text-[0.6875rem] font-semibold text-primary hover:underline"
              onClick={() => $businessLocalAiModalOpen.set(true)}
              type="button"
            >
              Install 2GB Local AI
            </button>
          )}
          <button
            className="text-[0.6875rem] text-muted-foreground hover:text-foreground"
            onClick={() => clearBusinessLocalAiMessages()}
            type="button"
          >
            Clear
          </button>
        </div>
      </div>

      <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
        {messages.map(msg => (
          <div
            className={cn(
              'rounded-xl px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap',
              msg.role === 'user' ? 'bg-muted/70 font-medium text-foreground' : 'bg-primary/5 text-foreground'
            )}
            key={msg.id}
          >
            <div>{msg.content}</div>
            {msg.role === 'assistant' && (msg.durationMs || msg.tokensPerSec) && (
              <div className="mt-1 text-[0.625rem] text-muted-foreground">
                {(msg.durationMs ? `${(msg.durationMs / 1000).toFixed(1)}s` : '') +
                  (msg.tokensPerSec ? ` · ${msg.tokensPerSec} tok/s` : '')}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="px-1 text-xs text-muted-foreground">Thinking locally...</div>}
      </div>
    </div>
  )
}

export interface BusinessLocalAiWorkspaceDrawerProps {
  document: BusinessDocument
  onApplyText?: (text: string) => void
}

export function BusinessLocalAiWorkspaceDrawer({
  document: doc,
  onApplyText
}: BusinessLocalAiWorkspaceDrawerProps) {
  const open = useStore($businessLocalAiDrawerOpen)
  const messages = useStore($businessLocalAiMessages)
  const busy = useStore($businessLocalAiChatBusy)
  const status = useStore($businessLocalAiStatus)
  const [input, setInput] = useState('')

  if (!IS_DESKTOP || !open) {
    return null
  }

  const handleSend = async (promptText: string) => {
    const trimmed = promptText.trim()

    if (!trimmed || busy) {
      return
    }

    setInput('')
    await askBusinessLocalAgent(trimmed, doc)
  }

  const handleInstantAudit = () => {
    const deterministicAudit = buildDeterministicDocumentAudit(doc)

    if (deterministicAudit) {
      $businessLocalAiMessages.set([
        ...$businessLocalAiMessages.get(),
        {
          content: deterministicAudit,
          createdAt: Date.now(),
          id: `biz-audit-${Date.now()}`,
          role: 'assistant'
        }
      ])
    }

    if (status?.installed) {
      void askBusinessLocalAgent(
        doc.language === 'fr'
          ? 'Donne 3 améliorations concrètes et courtes pour ce document.'
          : 'Give 3 concise, practical improvements for this document.',
        doc
      )
    }
  }

  return (
    <div className="border-b border-border/70 bg-muted/25 px-3 py-3 sm:px-6">
      <div className="mx-auto max-w-5xl space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Codicon className="text-primary" name="chip" size="0.95rem" />
            <span className="text-xs font-bold">Business Hub Local Agent</span>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[0.625rem] font-semibold text-primary">
              {status?.installed ? status.activeModelName : 'Not Installed'}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <button
              className="rounded-lg border border-border/70 bg-card px-2.5 py-1 text-[0.6875rem] font-semibold hover:border-primary/40"
              onClick={handleInstantAudit}
              type="button"
            >
              Audit & [to confirm]
            </button>
            <button
              className="rounded-lg border border-border/70 bg-card px-2.5 py-1 text-[0.6875rem] font-semibold hover:border-primary/40 disabled:opacity-50"
              disabled={busy}
              onClick={() =>
                void handleSend(
                  doc.language === 'fr'
                    ? 'Rédige une version concise et professionnelle de la section principale de ce document.'
                    : 'Draft a concise, professional version of the main section of this document.'
                )
              }
              type="button"
            >
              Draft / Improve
            </button>
            <button
              className="rounded-lg border border-border/70 bg-card px-2.5 py-1 text-[0.6875rem] font-semibold hover:border-primary/40"
              onClick={() => $businessLocalAiModalOpen.set(true)}
              type="button"
            >
              Model & RAM
            </button>
            <button
              aria-label="Close Local Agent drawer"
              className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => $businessLocalAiDrawerOpen.set(false)}
              type="button"
            >
              <Codicon name="close" size="0.85rem" />
            </button>
          </div>
        </div>

        {messages.length > 0 && (
          <div className="max-h-52 space-y-2 overflow-y-auto rounded-xl border border-border/60 bg-card/80 p-2.5">
            {messages.map(msg => (
              <div
                className={cn(
                  'rounded-lg px-2.5 py-2 text-xs leading-relaxed whitespace-pre-wrap',
                  msg.role === 'user' ? 'bg-muted/70 font-medium' : 'bg-primary/5'
                )}
                key={msg.id}
              >
                <div>{msg.content}</div>
                {msg.role === 'assistant' && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[0.625rem] text-muted-foreground">
                    {(msg.durationMs || msg.tokensPerSec) && (
                      <span>
                        {msg.durationMs ? `${(msg.durationMs / 1000).toFixed(1)}s` : ''}
                        {msg.tokensPerSec ? ` · ${msg.tokensPerSec} tok/s` : ''}
                      </span>
                    )}
                    {onApplyText && (
                      <button
                        className="rounded bg-primary/10 px-2 py-0.5 font-semibold text-primary hover:bg-primary/20"
                        onClick={() => onApplyText(msg.content)}
                        type="button"
                      >
                        Apply to Document
                      </button>
                    )}
                    <button
                      className="rounded border border-border/70 px-2 py-0.5 font-medium hover:text-foreground"
                      onClick={() => {
                        void navigator.clipboard?.writeText?.(msg.content)
                        notify({ kind: 'info', message: 'Copied to clipboard.', title: 'Copied' })
                      }}
                      type="button"
                    >
                      Copy
                    </button>
                  </div>
                )}
              </div>
            ))}
            {busy && <div className="px-1 text-xs text-muted-foreground">Generating locally...</div>}
          </div>
        )}

        <form
          className="flex items-center gap-2"
          onSubmit={event => {
            event.preventDefault()
            void handleSend(input)
          }}
        >
          <input
            aria-label="Ask Business Hub Local Agent"
            className="h-8 flex-1 rounded-xl border border-border/70 bg-background/90 px-3 text-xs focus:border-primary focus:outline-none"
            disabled={busy}
            onChange={event => setInput(event.target.value)}
            placeholder={
              doc.language === 'fr'
                ? 'Demandez à l’agent local (résumé, clause, reformulation, devis)...'
                : 'Ask the local agent (summary, clause, rewrite, quote notes)...'
            }
            value={input}
          />
          <button
            className="inline-flex h-8 items-center gap-1 rounded-xl bg-primary px-3 text-xs font-semibold text-primary-foreground transition hover:brightness-105 disabled:opacity-50"
            disabled={busy || !input.trim()}
            type="submit"
          >
            <Codicon name="send" size="0.8rem" />
            Ask
          </button>
        </form>
      </div>
    </div>
  )
}
