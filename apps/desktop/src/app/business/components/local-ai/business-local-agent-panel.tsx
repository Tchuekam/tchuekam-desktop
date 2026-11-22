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
      ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.6)]'
      : isInstalled && isEnabled
        ? 'bg-primary'
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
      className="inline-flex h-9 items-center gap-2 rounded-xl border border-border/80 bg-card/80 px-3 text-xs font-semibold shadow-2xs backdrop-blur-sm transition-all hover:border-primary/40 hover:bg-muted"
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 backdrop-blur-md sm:p-4"
      onClick={event => {
        if (event.target === event.currentTarget) {
          $businessLocalAiModalOpen.set(false)
        }
      }}
      role="dialog"
    >
      <div className="flex max-h-[90dvh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border/80 bg-card/95 text-foreground shadow-2xl backdrop-blur-xl">
        <div className="flex items-center justify-between gap-3 border-b border-border/60 bg-muted/20 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-xl bg-primary/15 text-primary">
              <Codicon name="chip" size="1.15rem" />
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
          <div className="grid grid-cols-1 gap-3 rounded-xl border border-border/70 bg-muted/25 p-3.5 sm:grid-cols-3">
            <div>
              <div className="text-[0.65rem] font-semibold uppercase tracking-wider text-muted-foreground">
                PC Hardware
              </div>
              <div className="mt-1 text-xs font-bold">
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
              <div className="mt-1 text-xs font-bold">
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
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-semibold text-primary-foreground transition hover:brightness-105 disabled:opacity-50"
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
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-semibold transition hover:border-amber-500/40 hover:text-amber-600 disabled:opacity-50"
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
            <div className="space-y-2 rounded-xl border border-primary/30 bg-primary/5 p-3.5">
              <div className="flex items-center justify-between gap-2 text-xs font-semibold">
                <span>{progress.message}</span>
                <span>
                  {typeof progress.percent === 'number' ? `${progress.percent}%` : '...'}
                  {progress.speedBps > 0 ? ` · ${formatSpeed(progress.speedBps)}` : ''}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-200"
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
                      model.active ? 'border-primary/50 bg-primary/5' : 'border-border/70 bg-background/60'
                    )}
                    key={model.id}
                  >
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-xs font-bold">{model.name}</span>
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[0.625rem] font-semibold text-muted-foreground">
                          {model.sizeMb} MB disk · ~{model.estimatedRamMb} MB RAM
                        </span>
                        <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[0.625rem] font-semibold text-primary">
                          {model.languages}
                        </span>
                        {model.recommendedForLowRam && (
                          <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[0.625rem] font-semibold text-emerald-600 dark:text-emerald-400">
                            Recommended 2GB PC
                          </span>
                        )}
                        {tooHeavy && (
                          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[0.625rem] font-semibold text-amber-600 dark:text-amber-400">
                            4GB+ RAM recommended
                          </span>
                        )}
