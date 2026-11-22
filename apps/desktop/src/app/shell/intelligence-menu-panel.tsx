import { useStore } from '@nanostores/react'

import {
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  dropdownMenuSectionLabel,
  DropdownMenuSeparator
} from '@/components/ui/dropdown-menu'
import { Brain, Check, Cpu, Download, Globe, Loader2, Play, Volume2, Zap } from '@/lib/icons'
import { cn } from '@/lib/utils'
import {
  $activeMbowaRoute,
  $intelligenceInstallingModel,
  $intelligenceLoading,
  $intelligenceStatus,
  installLocalModel,
  preloadLocalModel,
  refreshIntelligenceStatus,
  switchIntelligenceMode
} from '@/store/intelligence'
import type { IntelligenceMode } from '@/types/hermes'

const MODE_OPTIONS: ReadonlyArray<{
  description: string
  id: IntelligenceMode
  label: string
}> = [
  {
    description: 'Cloud online, automatic MbowaGPT offline failover',
    id: 'hybrid',
    label: 'Hybrid'
  },
  {
    description: 'Strict local MbowaGPT + offline Kokoro/Whisper voice',
    id: 'local',
    label: 'Local Offline'
  },
  {
    description: 'Cloud primary without automatic local pre-routing',
    id: 'online',
    label: 'Online'
  }
]

export function IntelligenceMenuPanel() {
  const status = useStore($intelligenceStatus)
  const loading = useStore($intelligenceLoading)
  const installingModel = useStore($intelligenceInstallingModel)
  const activeRoute = useStore($activeMbowaRoute)

  const mode = status?.mode ?? 'hybrid'
  const connectivity = status?.connectivity ?? 'online'
  const activeTier = status?.active_tier ?? 'cloud'
  const models = status?.local_runtime?.models ?? []
  const hw = status?.local_runtime?.hardware

  const connectivityLabel =
    connectivity === 'offline' ? 'Offline' : connectivity === 'degraded' ? 'Degraded' : 'Online'

  const connectivityTone =
    connectivity === 'offline'
      ? 'bg-amber-500/15 text-amber-400'
      : connectivity === 'degraded'
        ? 'bg-yellow-500/15 text-yellow-400'
        : 'bg-emerald-500/15 text-emerald-400'

  return (
    <>
      <DropdownMenuGroup>
        <div className="flex items-center justify-between gap-2 px-2 py-1.5">
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground">
            <Brain className="size-3.5 text-primary" />
            Intelligence Engine
          </span>
          <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', connectivityTone)}>
            {connectivityLabel} · {activeTier === 'local' ? 'Local' : 'Cloud'}
          </span>
        </div>
        {activeRoute?.display_name ? (
          <div className="px-2 pb-1 text-[11px] text-muted-foreground">
            Active specialist: <span className="font-medium text-foreground">{activeRoute.display_name}</span>
          </div>
        ) : null}
      </DropdownMenuGroup>

      <DropdownMenuSeparator />

      <DropdownMenuGroup>
        <DropdownMenuLabel className={dropdownMenuSectionLabel}>Operating Mode</DropdownMenuLabel>
        {MODE_OPTIONS.map(option => {
          const selected = mode === option.id

          return (
            <DropdownMenuItem
              disabled={loading}
              key={option.id}
              onSelect={event => {
                event.preventDefault()
                void switchIntelligenceMode(option.id)
              }}
            >
              <span className="flex w-4 shrink-0 items-center justify-center">
                {selected ? <Check className="size-3.5 text-primary" /> : <Globe className="size-3 opacity-50" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-medium">{option.label}</span>
                <span className="block truncate text-[10px] text-muted-foreground">{option.description}</span>
              </span>
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuGroup>

      <DropdownMenuSeparator />

      <DropdownMenuGroup>
        <DropdownMenuLabel className={dropdownMenuSectionLabel}>
          MbowaGPT Local Ecosystem
          {hw ? ` (${hw.ram_gb}GB RAM · ctx ${hw.recommended_ctx_size})` : ''}
        </DropdownMenuLabel>
        {models.map(m => {
          const isBusy = installingModel === m.id
          const isRunning = status?.local_runtime?.active_role === m.id && status?.local_runtime?.running

          return (
            <div
              className="flex items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-xs hover:bg-accent/40"
              key={m.id}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <Cpu className="size-3 shrink-0 opacity-70" />
                  <span className="truncate font-medium text-foreground">{m.display_name}</span>
                  {isRunning ? (
                    <span className="rounded bg-emerald-500/15 px-1 text-[9px] text-emerald-400">Active</span>
                  ) : null}
                </div>
                <div className="truncate pl-4.5 text-[10px] text-muted-foreground">
                  {m.resolved_weights || `${m.recommended_filename} (${m.recommended_size_mb} MB)`}
                </div>
              </div>
              {m.ready ? (
                <button
                  className="inline-flex shrink-0 items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
                  disabled={isBusy}
                  onClick={() => void preloadLocalModel(m.id)}
                  title="Warm up local model in memory"
                  type="button"
                >
                  {isBusy ? <Loader2 className="size-2.5 animate-spin" /> : <Play className="size-2.5" />}
                  {isRunning ? 'Warm' : 'Load'}
                </button>
              ) : (
                <button
                  className="inline-flex shrink-0 items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] text-primary hover:bg-accent disabled:opacity-50"
                  disabled={isBusy || connectivity === 'offline'}
                  onClick={() => void installLocalModel(m.id)}
                  title="Download recommended offline weights"
                  type="button"
                >
                  {isBusy ? <Loader2 className="size-2.5 animate-spin" /> : <Download className="size-2.5" />}
                  Install
                </button>
              )}
            </div>
          )
        })}
      </DropdownMenuGroup>

      <DropdownMenuSeparator />

      {status?.autonomy ? (
        <>
          <DropdownMenuGroup>
            <DropdownMenuLabel className={dropdownMenuSectionLabel}>
              Autonomous Engine · {status.autonomy.self_conscious ? 'Self-Conscious' : 'Active'}
            </DropdownMenuLabel>
            <div className="space-y-1 px-2 py-1 text-[10px] text-muted-foreground">
              <div className="flex items-center justify-between">
                <span>Unified Tool Ecosystem</span>
                <span className="font-medium text-foreground">
                  {status.autonomy.tool_health.total_registered} tools · {status.autonomy.tool_health.success_rate}% reliable
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Skills Ecosystem</span>
                <span className="font-medium text-foreground">
                  {status.autonomy.skills_ecosystem.domains_covered}/{status.autonomy.skills_ecosystem.domains_total} domains ({status.autonomy.skills_ecosystem.total_skills} skills)
                </span>
              </div>
              {status.autonomy.active_plan ? (
                <div className="flex items-center justify-between">
                  <span className="truncate pr-2">Plan: {status.autonomy.active_plan.objective}</span>
                  <span className="shrink-0 font-medium text-emerald-400">
                    {status.autonomy.active_plan.completed_steps}/{status.autonomy.active_plan.total_steps} steps
                  </span>
                </div>
              ) : null}
            </div>
          </DropdownMenuGroup>

          <DropdownMenuSeparator />
        </>
      ) : null}

      <DropdownMenuGroup>
        <div className="flex items-center justify-between px-2 py-1 text-[10px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Volume2 className="size-3" />
            Offline Voice: {status?.voice?.kokoro_ready ? 'Kokoro + Whisper Ready' : 'Whisper Ready'}
          </span>
          <button
            className="inline-flex items-center gap-1 text-[10px] hover:text-foreground"
            disabled={loading}
            onClick={() => void refreshIntelligenceStatus(true)}
            type="button"
          >
            {loading ? <Loader2 className="size-2.5 animate-spin" /> : <Zap className="size-2.5" />}
            Refresh
          </button>
        </div>
      </DropdownMenuGroup>
    </>
  )
}
