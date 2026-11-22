import { useStore } from '@nanostores/react'
import { useEffect, useRef } from 'react'

import { Button } from '@/components/ui/button'
import { Loader2, Mic, Volume2, VolumeX } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { stopVoicePlayback } from '@/lib/voice-playback'
import { $voicePlayback } from '@/store/voice-playback'

import type { VoiceActivityState } from './types'

type BrowserAudioContext = typeof AudioContext

interface ElementAnalyser {
  analyser: AnalyserNode
}

const elementAnalysers = new WeakMap<HTMLAudioElement, ElementAnalyser>()
let playbackAudioContext: AudioContext | null = null

function getPlaybackAudioContext(): AudioContext | null {
  if (playbackAudioContext && playbackAudioContext.state !== 'closed') {
    return playbackAudioContext
  }

  const audioWindow = window as Window & { webkitAudioContext?: BrowserAudioContext }
  const AudioContextCtor = window.AudioContext || audioWindow.webkitAudioContext

  if (!AudioContextCtor) {
    return null
  }

  playbackAudioContext = new AudioContextCtor()

  return playbackAudioContext
}

function formatElapsed(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(safeSeconds / 60)
  const remainingSeconds = safeSeconds % 60

  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
}

function VoiceLevelBars({ level, active }: { active: boolean; level: number }) {
  const normalized = Math.max(0, Math.min(level, 1))
  const bars = [0.38, 0.65, 0.88, 1, 0.88, 0.65, 0.38]

  return (
    <div aria-hidden="true" className="flex h-4 items-center gap-[0.1875rem] text-(--tk-cyan)">
      {bars.map((weight, index) => {
        const height = active ? 0.24 + Math.min(0.76, normalized * weight) : 0.24

        return (
          <span
            className={cn(
              'w-[0.125rem] rounded-full bg-current transition-[height,opacity] duration-75 ease-out',
              active ? 'opacity-90' : 'animate-pulse opacity-45'
            )}
            key={index}
            style={{ height: `${height * 100}%` }}
          />
        )
      })}
    </div>
  )
}

function getElementAnalyser(audioElement: HTMLAudioElement): ElementAnalyser | null {
  try {
    let entry = elementAnalysers.get(audioElement)

    if (!entry) {
      const context = getPlaybackAudioContext()

      if (!context) {
        return null
      }

      const source = context.createMediaElementSource(audioElement)
      const analyser = context.createAnalyser()

      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.65
      source.connect(analyser)
      analyser.connect(context.destination)
      entry = { analyser }
      elementAnalysers.set(audioElement, entry)
    }

    void playbackAudioContext?.resume()

    return entry
  } catch {
    return null
  }
}

const WAVE_W = 88
const WAVE_H = 16
const BAR_W = 2
const BAR_GAP = 5
const STEP = BAR_W + BAR_GAP
const BARS = Math.floor((WAVE_W + BAR_GAP) / STEP)
const X0 = Math.round((WAVE_W - (BARS * STEP - BAR_GAP)) / 2)

function PlaybackWaveform({ audioElement }: { audioElement: HTMLAudioElement | null }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current

    if (!canvas || !audioElement) {
      return
    }

    const entry = getElementAnalyser(audioElement)
    const ctx = canvas.getContext('2d')

    if (!entry || !ctx) {
      return
    }

    const dpr = Math.max(1, window.devicePixelRatio || 1)
    const { analyser } = entry
    const buf = new Uint8Array(analyser.frequencyBinCount)
    const hi = Math.floor(buf.length * 0.9)

    canvas.width = Math.round(WAVE_W * dpr)
    canvas.height = Math.round(WAVE_H * dpr)
    canvas.style.width = `${WAVE_W}px`
    canvas.style.height = `${WAVE_H}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.imageSmoothingEnabled = false
    const style = getComputedStyle(canvas)

    if (typeof ctx.createLinearGradient === 'function') {
      const rootStyle = getComputedStyle(document.documentElement)
      const indigo = rootStyle.getPropertyValue('--tk-indigo').trim() || style.color
      const cyan = rootStyle.getPropertyValue('--tk-cyan').trim() || style.color
      const grad = ctx.createLinearGradient(0, 0, WAVE_W, 0)
      grad.addColorStop(0, indigo)
      grad.addColorStop(1, cyan)
      ctx.fillStyle = grad
    } else {
      ctx.fillStyle = style.color
    }

    let raf = 0

    const tick = () => {
      analyser.getByteFrequencyData(buf)
      ctx.clearRect(0, 0, WAVE_W, WAVE_H)

      for (let i = 0; i < BARS; i++) {
        const a = Math.floor((i / BARS) * hi)
        const b = Math.floor(((i + 1) / BARS) * hi)
        let peak = 0

        for (let j = a; j < b; j++) {
          peak = Math.max(peak, buf[j] ?? 0)
        }

        const amp = Math.sqrt(peak / 255)
        const bh = Math.max(3, Math.round((0.18 + amp * 0.82) * WAVE_H))
        const x = X0 + i * STEP
        const y = Math.round((WAVE_H - bh) / 2)

        if (typeof ctx.roundRect === 'function') {
          ctx.beginPath()
          ctx.roundRect(x, y, BAR_W, bh, Math.min(BAR_W / 2, bh / 2))
          ctx.fill()
        } else {
          ctx.fillRect(x, y, BAR_W, bh)
        }
      }

      raf = requestAnimationFrame(tick)
    }

    tick()

    return () => cancelAnimationFrame(raf)
  }, [audioElement])

  return <canvas aria-hidden="true" className="block h-4 w-[88px]" ref={canvasRef} />
}

export function VoiceActivity({ state }: { state: VoiceActivityState }) {
  if (state.status === 'idle') {
    return null
  }

  const recording = state.status === 'recording'
  const title = recording ? 'Dictating' : 'Transcribing'

  return (
    <div
      aria-live="polite"
      className={cn(
        'flex h-8.5 items-center gap-2.5 rounded-xl border border-(--tk-cyan-border) bg-(--tk-cyan-soft) px-3 text-xs text-(--tk-cyan-text)',
        'shadow-[inset_0_1px_0_var(--tk-specular-edge)] backdrop-blur-md'
      )}
      role="status"
    >
      <div
        className={cn(
          'flex size-5 shrink-0 items-center justify-center rounded-full',
          recording ? 'bg-(--tk-cyan) text-white shadow-xs' : 'bg-(--tk-indigo-soft) text-(--tk-indigo-text)'
        )}
      >
        {recording ? <Mic size={11} /> : <Loader2 className="animate-spin" size={11} />}
      </div>

      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span className="truncate font-medium text-foreground/92">{title}</span>
        <span className="font-mono text-[0.6875rem] tabular-nums text-(--ui-text-secondary)">
          {formatElapsed(state.elapsedSeconds)}
        </span>
      </div>

      <VoiceLevelBars active={recording} level={state.level} />
    </div>
  )
}

export function VoicePlaybackActivity() {
  const playback = useStore($voicePlayback)

  if (playback.status === 'idle') {
    return null
  }

  const preparing = playback.status === 'preparing'

  const title = preparing
    ? 'Preparing audio'
    : playback.source === 'voice-conversation'
      ? 'Speaking response'
      : 'Reading aloud'

  return (
    <div
      aria-live="polite"
      className={cn(
        'flex h-8.5 items-center gap-2.5 rounded-xl border border-(--tk-indigo-border) bg-(--tk-indigo-soft) px-3 text-xs text-(--tk-indigo-text)',
        'shadow-[inset_0_1px_0_var(--tk-specular-edge)] backdrop-blur-md'
      )}
      role="status"
    >
      <div className="flex size-5 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-(--tk-indigo) to-(--tk-cyan) text-white shadow-xs">
        {preparing ? <Loader2 className="animate-spin" size={11} /> : <Volume2 size={11} />}
      </div>

      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span className="truncate font-medium text-foreground/92">{title}</span>
        {!preparing && <PlaybackWaveform audioElement={playback.audioElement} />}
      </div>

      <Button
        className="h-6 shrink-0 gap-1 rounded-full px-2.5 text-[0.6875rem] font-medium hover:bg-(--tk-indigo-soft) hover:text-foreground"
        onClick={stopVoicePlayback}
        size="sm"
        type="button"
        variant="ghost"
      >
        <VolumeX size={12} />
        Stop
      </Button>
    </div>
  )
}
