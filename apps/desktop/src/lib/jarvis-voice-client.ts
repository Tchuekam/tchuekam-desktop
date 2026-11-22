import { buildVoiceWsUrl } from '@/hermes'
import type { IntelligenceRouteEvent } from '@/types/hermes'

export type JarvisVoiceState = 'idle' | 'listening' | 'speaking' | 'thinking' | 'transcribing'

export interface JarvisVoiceClientCallbacks {
  onAssistantDelta?: (delta: string, generationId: number) => void
  onAssistantFinal?: (payload: {
    generation_id?: number
    model?: string
    provider?: string
    specialist?: string | null
    text: string
  }) => void
  onClose?: () => void
  onError?: (error: Error) => void
  onIntelligence?: (route: IntelligenceRouteEvent) => void
  onLevel?: (level: number) => void
  onReady?: (payload: {
    session_id: string
    stt_provider?: string
    tts_provider?: string
  }) => void
  onStateChange?: (state: JarvisVoiceState) => void
  onTranscript?: (text: string, provider?: string) => void
}

export interface JarvisVoiceStartOptions {
  bargeIn?: boolean
  language?: string
  sessionId?: null | string
  voice?: string
}

export function isJarvisDuplexVoiceSupported(): boolean {
  if (typeof window === 'undefined') {
    return false
  }

  if (typeof WebSocket === 'undefined') {
    return false
  }

  if (typeof AudioContext === 'undefined' || typeof AudioWorkletNode === 'undefined') {
    return false
  }

  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    return false
  }

  return true
}

export class JarvisVoiceClient {
  private callbacks: JarvisVoiceClientCallbacks
  private captureCtx: AudioContext | null = null
  private playbackCtx: AudioContext | null = null
  private captureNode: AudioWorkletNode | null = null
  private playbackNode: AudioWorkletNode | null = null
  private mediaStream: MediaStream | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private ws: WebSocket | null = null
  private closed = false
  private ready = false

  constructor(callbacks: JarvisVoiceClientCallbacks = {}) {
    this.callbacks = callbacks
  }

  async start(options: JarvisVoiceStartOptions = {}): Promise<void> {
    this.closed = false
    this.ready = false

    const wsUrl = await buildVoiceWsUrl(options.sessionId ?? undefined)
    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    this.ws = ws

    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        reject(new Error('Voice WebSocket connection timed out'))
      }, 6000)

      ws.onopen = () => {
        window.clearTimeout(timeout)
        ws.send(
          JSON.stringify({
            barge_in: options.bargeIn ?? true,
            language: options.language || 'auto',
            session_id: options.sessionId || undefined,
            type: 'config',
            voice: options.voice || ''
          })
        )
        resolve()
      }

      ws.onerror = () => {
        window.clearTimeout(timeout)
        reject(new Error('Voice WebSocket failed to connect'))
      }

      ws.onmessage = event => {
        this.handleMessage(event)
      }

      ws.onclose = () => {
        window.clearTimeout(timeout)

        if (!this.closed) {
          this.callbacks.onClose?.()
        }
      }
    })

    if (this.closed) {
      return
    }

    await this.setupAudioPipelines()
  }

  private async setupAudioPipelines(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        autoGainControl: true,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000
      }
    })

    if (this.closed) {
      stream.getTracks().forEach(t => t.stop())

      return
    }

    this.mediaStream = stream

    const captureCtx = new AudioContext({ sampleRate: 16000 })
    this.captureCtx = captureCtx
    await captureCtx.audioWorklet.addModule('./audio-worklets/pcmWorkletProcessor.js')
    const captureNode = new AudioWorkletNode(captureCtx, 'pcm-worklet-processor')
    this.captureNode = captureNode

    captureNode.port.onmessage = event => {
      const payload = event.data as { buffer?: ArrayBuffer; rms?: number } | ArrayBuffer

      if (this.closed || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
        return
      }

      if (payload instanceof ArrayBuffer) {
        this.ws.send(payload)

        return
      }

      if (typeof payload?.rms === 'number') {
        this.callbacks.onLevel?.(Math.min(1, payload.rms * 3.2))
      }

      if (payload?.buffer instanceof ArrayBuffer) {
        this.ws.send(payload.buffer)
      }
    }

    const source = captureCtx.createMediaStreamSource(stream)
    this.sourceNode = source
    source.connect(captureNode)

    const playbackCtx = new AudioContext({ sampleRate: 24000 })
    this.playbackCtx = playbackCtx
    await playbackCtx.audioWorklet.addModule('./audio-worklets/ttsPlaybackProcessor.js')
    const playbackNode = new AudioWorkletNode(playbackCtx, 'tts-playback-processor')
    this.playbackNode = playbackNode
    playbackNode.connect(playbackCtx.destination)

    if (captureCtx.state === 'suspended') {
      await captureCtx.resume()
    }

    if (playbackCtx.state === 'suspended') {
      await playbackCtx.resume()
    }
  }

  private handleMessage(event: MessageEvent): void {
    if (typeof event.data === 'string') {
      try {
        const msg = JSON.parse(event.data) as Record<string, unknown>
        const type = String(msg.type || '')

        if (type === 'voice_ready') {
          this.ready = true
          this.callbacks.onReady?.({
            session_id: String(msg.session_id || ''),
            stt_provider: typeof msg.stt_provider === 'string' ? msg.stt_provider : undefined,
            tts_provider: typeof msg.tts_provider === 'string' ? msg.tts_provider : undefined
          })

          return
        }

        if (type === 'state') {
          const state = String(msg.state || 'listening') as JarvisVoiceState
          this.callbacks.onStateChange?.(state)

          return
        }

        if (type === 'transcript_final') {
          this.callbacks.onTranscript?.(
            String(msg.text || ''),
            typeof msg.provider === 'string' ? msg.provider : undefined
          )

          return
        }

        if (type === 'assistant_delta') {
          this.callbacks.onAssistantDelta?.(
            String(msg.delta || ''),
            Number(msg.generation_id || 0)
          )

          return
        }

        if (type === 'assistant_final') {
          this.callbacks.onAssistantFinal?.({
            generation_id: Number(msg.generation_id || 0),
            model: typeof msg.model === 'string' ? msg.model : undefined,
            provider: typeof msg.provider === 'string' ? msg.provider : undefined,
            specialist: typeof msg.specialist === 'string' ? msg.specialist : null,
            text: String(msg.text || '')
          })

          return
        }

        if (type === 'tts_clear') {
          this.flushPlayback()

          return
        }

        if (type === 'intelligence') {
          this.callbacks.onIntelligence?.(msg as unknown as IntelligenceRouteEvent)

          return
        }

        if (type === 'error') {
          this.callbacks.onError?.(new Error(String(msg.error || 'Voice error')))
        }
      } catch {
        // Ignore malformed JSON control frame
      }

      return
    }

    if (event.data instanceof ArrayBuffer && this.playbackNode) {
      if (this.playbackCtx?.state === 'suspended') {
        void this.playbackCtx.resume()
      }

      const chunk = new Int16Array(event.data)
      this.playbackNode.port.postMessage(chunk)
    }
  }

  flushPlayback(): void {
    this.playbackNode?.port.postMessage({ type: 'clear' })
  }

  interrupt(reason = 'user_interrupt'): void {
    this.flushPlayback()
    this.sendControl({ reason, type: 'interrupt' })
  }

  sendControl(payload: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload))
    }
  }

  isReady(): boolean {
    return this.ready
  }

  async stop(): Promise<void> {
    this.closed = true
    this.flushPlayback()

    try {
      this.ws?.close()
    } catch {
      // ignore
    }

    this.ws = null

    try {
      this.sourceNode?.disconnect()
      this.captureNode?.disconnect()
      this.playbackNode?.disconnect()
    } catch {
      // ignore
    }

    this.sourceNode = null
    this.captureNode = null
    this.playbackNode = null

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(t => t.stop())
      this.mediaStream = null
    }

    await Promise.allSettled([
      this.captureCtx ? this.captureCtx.close() : Promise.resolve(),
      this.playbackCtx ? this.playbackCtx.close() : Promise.resolve()
    ])
    this.captureCtx = null
    this.playbackCtx = null
  }
}
