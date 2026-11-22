import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { triggerHaptic } from '@/lib/haptics'
import { AudioLines, Layers3, Loader2, Square } from '@/lib/icons'
import { cn } from '@/lib/utils'

import type { ConversationStatus } from './hooks/use-voice-conversation'
import type { ChatBarState, VoiceStatus } from './types'

export const ICON_BTN = 'size-(--composer-control-size) shrink-0 rounded-lg transition-all duration-150'
export const GHOST_ICON_BTN = cn(
  ICON_BTN,
  'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
)
// Primary focal CTA for sending, queueing, or entering voice conversation.
// Uses the signature top-lit electric indigo treatment so the composer
// reads as an intentional, precision-engineered control deck.
export const PRIMARY_ICON_BTN = cn(
  'tk-btn-primary size-(--composer-control-primary-size,var(--composer-control-size)) shrink-0 rounded-full p-0 text-white',
  'active:scale-95 disabled:opacity-35 disabled:shadow-none'
)

interface ConversationProps {
  active: boolean
  level: number
  muted: boolean
  status: ConversationStatus
  onEnd: () => void
  onStart: () => void
  onStopTurn: () => void
  onToggleMute: () => void
}

export function ComposerControls({
  busy,
  busyAction,
  canSubmit,
  conversation,
  disabled,
  hasComposerPayload,
  state,
  voiceStatus,
  onDictate
}: {
  busy: boolean
  busyAction: 'queue' | 'stop'
  canSubmit: boolean
  conversation: ConversationProps
  disabled: boolean
  hasComposerPayload: boolean
  state: ChatBarState
  voiceStatus: VoiceStatus
  onDictate: () => void
}) {
  if (conversation.active) {
    return <ConversationPill {...conversation} disabled={disabled} />
  }

  const showVoicePrimary = !busy && !hasComposerPayload
  const isStop = busy && busyAction === 'stop'

  return (
    <div className="ml-auto flex shrink-0 items-center gap-(--composer-control-gap)">
      <DictationButton disabled={disabled} onToggle={onDictate} state={state.voice} status={voiceStatus} />
      {showVoicePrimary ? (
        <Button
          aria-label="Start voice conversation"
          className={PRIMARY_ICON_BTN}
          disabled={disabled}
          onClick={() => {
            triggerHaptic('open')
            conversation.onStart()
          }}
          size="icon"
          title="Start voice conversation"
          type="button"
        >
          <AudioLines size={17} />
        </Button>
      ) : (
        <Button
          aria-label={busy ? (busyAction === 'queue' ? 'Queue message' : 'Stop') : 'Send'}
          className={cn(
            isStop
              ? 'size-(--composer-control-primary-size,var(--composer-control-size)) shrink-0 rounded-full border border-destructive/40 bg-destructive/90 p-0 text-white shadow-xs transition-all duration-150 hover:bg-destructive active:scale-95 disabled:opacity-35'
              : PRIMARY_ICON_BTN
          )}
          disabled={disabled || !canSubmit}
          title={busy ? (busyAction === 'queue' ? 'Queue message' : 'Stop') : 'Send'}
          type="submit"
        >
          {busy ? (
            busyAction === 'queue' ? (
              <Layers3 size={16} />
            ) : (
              <span className="block size-2.5 rounded-[0.1875rem] bg-current" />
            )
          ) : (
            <Codicon name="arrow-up" size="1rem" />
          )}
        </Button>
      )}
    </div>
  )
}

function ConversationPill({
  disabled,
  level,
  muted,
  onEnd,
  onStopTurn,
  onToggleMute,
  status
}: ConversationProps & { disabled: boolean }) {
  const speaking = status === 'speaking'
  const listening = status === 'listening' && !muted

  const shortStatus =
    status === 'speaking'
      ? 'Speaking'
      : status === 'transcribing'
        ? 'Transcribing'
        : status === 'thinking'
          ? 'Thinking'
          : muted
            ? 'Muted'
            : 'Listening'

  const label =
    status === 'speaking'
      ? 'Speaking · Interrupt anytime'
      : status === 'transcribing'
        ? 'Transcribing'
        : status === 'thinking'
          ? 'Thinking'
          : muted
            ? 'Muted'
            : 'Listening'

  return (
    <div className="ml-auto flex shrink-0 items-center gap-1 rounded-full border border-(--tk-cyan-border) bg-(--tk-voice-surface) px-1.5 py-0.5 shadow-(--tk-voice-shadow) backdrop-blur-md">
      <span aria-hidden="true" className="hidden items-center gap-1.5 pl-2 pr-1 text-[0.7rem] font-medium text-foreground/85 sm:inline-flex">
        <span
          className={cn(
            'size-1.5 rounded-full',
            speaking || status === 'thinking'
              ? 'tk-thinking-dot'
              : listening
                ? 'bg-(--tk-cyan) animate-pulse'
                : 'bg-muted-foreground/60'
          )}
        />
        <span>{shortStatus}</span>
      </span>
      <Button
        aria-label={muted ? 'Unmute microphone' : 'Mute microphone'}
        aria-pressed={muted}
        className={cn(
          'size-7 shrink-0 rounded-full p-0 text-(--ui-text-secondary) transition-colors hover:bg-(--tk-cyan-soft) hover:text-foreground',
          muted && 'bg-muted/80 text-muted-foreground'
        )}
        disabled={disabled}
        onClick={() => {
          triggerHaptic('selection')
          onToggleMute()
        }}
        size="icon"
        title={muted ? 'Unmute microphone' : 'Mute microphone'}
        type="button"
        variant="ghost"
      >
        <Codicon name={muted ? 'mic-off' : 'mic'} size="1rem" />
      </Button>
      {(listening || speaking) && (
        <Button
          aria-label={speaking ? 'Interrupt assistant speech' : 'Stop listening and send'}
          className="h-(--composer-control-size) shrink-0 gap-1.5 rounded-full px-2.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          disabled={disabled}
          onClick={() => {
            triggerHaptic('submit')
            onStopTurn()
          }}
          title={speaking ? 'Interrupt speech' : 'Stop listening and send'}
          type="button"
          variant="ghost"
        >
          <Square className="fill-current" size={11} />
          <span>{speaking ? 'Interrupt' : 'Stop'}</span>
        </Button>
      )}
      <Button
        aria-label="End voice conversation"
        className="h-(--composer-control-size) gap-1.5 rounded-full bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        disabled={disabled}
        onClick={() => {
          triggerHaptic('close')
          onEnd()
        }}
        title="End voice conversation"
        type="button"
      >
        <ConversationIndicator level={level} listening={listening} speaking={speaking} />
        <span>End</span>
      </Button>
      <span className="sr-only" role="status">
        {label}
      </span>
    </div>
  )
}

function ConversationIndicator({
  level,
  listening,
  speaking
}: {
  level: number
  listening: boolean
  speaking: boolean
}) {
  if (speaking) {
    return <Loader2 className="animate-spin" size={12} />
  }

  const bars = [0.55, 0.85, 1, 0.85, 0.55]
  const normalized = Math.max(0, Math.min(level, 1))

  return (
    <span aria-hidden="true" className="flex h-3 items-center gap-0.5">
      {bars.map((weight, index) => {
        const height = listening ? 0.3 + Math.min(0.7, normalized * weight) : 0.3

        return <span className="w-0.5 rounded-full bg-current" key={index} style={{ height: `${height * 100}%` }} />
      })}
    </span>
  )
}

function DictationButton({
  disabled,
  state,
  status,
  onToggle
}: {
  disabled: boolean
  state: ChatBarState['voice']
  status: VoiceStatus
  onToggle: () => void
}) {
  const active = state.active || status !== 'idle'

  const aria =
    status === 'recording' ? 'Stop dictation' : status === 'transcribing' ? 'Transcribing dictation' : 'Voice dictation'

  return (
    <Button
      aria-label={aria}
      aria-pressed={active}
      className={cn(
        GHOST_ICON_BTN,
        'p-0',
        'data-[active=true]:bg-accent data-[active=true]:text-foreground',
        status === 'recording' && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary',
        status === 'transcribing' && 'bg-primary/10 text-primary'
      )}
      data-active={active}
      disabled={disabled || !state.enabled || status === 'transcribing'}
      onClick={() => {
        triggerHaptic(active ? 'close' : 'open')
        onToggle()
      }}
      size="icon"
      title={aria}
      type="button"
      variant="ghost"
    >
      {status === 'recording' ? (
        <Square className="fill-current" size={12} />
      ) : status === 'transcribing' ? (
        <Loader2 className="animate-spin" size={16} />
      ) : (
        <Codicon name="mic" size="1rem" />
      )}
    </Button>
  )
}
