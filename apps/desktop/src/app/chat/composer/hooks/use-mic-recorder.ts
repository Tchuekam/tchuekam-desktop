import { useEffect, useRef, useState } from 'react'

type BrowserAudioContext = typeof AudioContext

export interface MicRecorderOptions {
  idleSilenceMs?: number
  maxDipMs?: number
  minSpeechMs?: number
  onError?: (error: Error) => void
  onLevel?: (level: number) => void
  onSilence?: () => void
  onSpeechStart?: () => void
  silenceLevel?: number
  silenceMs?: number
}

export interface MicRecording {
  audio: Blob
  durationMs: number
  heardSpeech: boolean
}

interface MicRecorderHandle {
  start: (options?: MicRecorderOptions) => Promise<void>
  stop: () => Promise<MicRecording | null>
  cancel: () => void
}

function micError(error: unknown): Error {
  const name = error instanceof DOMException ? error.name : ''

  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return new Error('Microphone permission was denied.')
  }

  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return new Error('No microphone was found.')
  }

  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return new Error('Microphone is already in use by another app.')
  }

  if (name === 'OverconstrainedError') {
    return new Error('Microphone constraints are not supported by this device.')
  }

  if (error instanceof Error) {
    return error
  }

  return new Error('Could not start microphone recording.')
}

export function useMicRecorder(): { handle: MicRecorderHandle; level: number; recording: boolean } {
  const [level, setLevel] = useState(0)
  const [recording, setRecording] = useState(false)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioContextRef = useRef<AudioContext | null>(null)
  const animationRef = useRef<number | null>(null)
  const startedAtRef = useRef(0)
  const heardSpeechRef = useRef(false)
  const speechStartedAtRef = useRef<number | null>(null)
  const speechDipStartedAtRef = useRef<number | null>(null)
  const noiseFloorRef = useRef(0.015)
  const silenceTriggeredRef = useRef(false)
  const silenceStartedAtRef = useRef<number | null>(null)
  const stopResolverRef = useRef<((recording: MicRecording | null) => void) | null>(null)

  const cleanup = () => {
    if (animationRef.current) {
      window.cancelAnimationFrame(animationRef.current)
      animationRef.current = null
    }

    void audioContextRef.current?.close()
    audioContextRef.current = null
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
    recorderRef.current = null
    setLevel(0)
    setRecording(false)
    speechStartedAtRef.current = null
    speechDipStartedAtRef.current = null
    silenceTriggeredRef.current = false
  }

  useEffect(() => () => cleanup(), [])

  const startMeter = (stream: MediaStream, options: MicRecorderOptions) => {
    const audioWindow = window as Window & { webkitAudioContext?: BrowserAudioContext }
    const AudioContextCtor = window.AudioContext || audioWindow.webkitAudioContext

    if (!AudioContextCtor) {
      return
    }

    try {
      const audioContext = new AudioContextCtor()
      void audioContext.resume()
      const analyser = audioContext.createAnalyser()
      const source = audioContext.createMediaStreamSource(stream)

      analyser.fftSize = 256
      const data = new Uint8Array(analyser.fftSize)

      source.connect(analyser)
      audioContextRef.current = audioContext

      const tick = () => {
        analyser.getByteTimeDomainData(data)

        let sum = 0

        for (const value of data) {
          const centered = value - 128
          sum += centered * centered
        }

        const rms = Math.sqrt(sum / data.length)
        const normalized = Math.min(1, rms / 42)
        const now = Date.now()

        setLevel(normalized)
        options.onLevel?.(normalized)

        const speechThreshold = options.silenceLevel ?? 0
        const silenceMs = options.silenceMs ?? 0
        const idleSilenceMs = options.idleSilenceMs ?? 0
        const minSpeechMs = options.minSpeechMs ?? 260
        const maxDipMs = options.maxDipMs ?? 220

        if (!heardSpeechRef.current && speechStartedAtRef.current === null) {
          noiseFloorRef.current = noiseFloorRef.current * 0.96 + normalized * 0.04
        }

        const effectiveThreshold =
          speechThreshold > 0 ? Math.max(speechThreshold, Math.min(0.18, noiseFloorRef.current * 2.2)) : 0

        if (effectiveThreshold > 0 && options.onSilence && !silenceTriggeredRef.current) {
          if (normalized >= effectiveThreshold) {
            speechStartedAtRef.current ??= now
            speechDipStartedAtRef.current = null
            silenceStartedAtRef.current = null

            if (!heardSpeechRef.current && now - speechStartedAtRef.current >= minSpeechMs) {
              heardSpeechRef.current = true
              options.onSpeechStart?.()
            }
          } else if (heardSpeechRef.current && silenceMs > 0) {
            silenceStartedAtRef.current ??= now

            if (now - silenceStartedAtRef.current >= silenceMs) {
              silenceTriggeredRef.current = true
              options.onSilence()

              return
            }
          } else {
            if (speechStartedAtRef.current !== null) {
              speechDipStartedAtRef.current ??= now

              if (now - speechDipStartedAtRef.current >= maxDipMs) {
                speechStartedAtRef.current = null
                speechDipStartedAtRef.current = null
              }
            }

            if (!heardSpeechRef.current && idleSilenceMs > 0 && now - startedAtRef.current >= idleSilenceMs) {
              silenceTriggeredRef.current = true
              options.onSilence()

              return
            }
          }
        }

        animationRef.current = window.requestAnimationFrame(tick)
      }

      tick()
    } catch {
      setLevel(0)
    }
  }

  const start: MicRecorderHandle['start'] = async (options = {}) => {
    if (recorderRef.current) {
      return
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      throw new Error('This runtime does not support microphone recording.')
    }

    const permitted = await window.hermesDesktop?.requestMicrophoneAccess?.()

    if (permitted === false) {
      throw new Error('Microphone access denied.')
    }

    let stream: MediaStream

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { autoGainControl: true, echoCancellation: true, noiseSuppression: true }
      })
    } catch (error) {
      throw micError(error)
    }

    const mimeType =
      ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg', 'audio/wav'].find(
        type => MediaRecorder.isTypeSupported(type)
      ) ?? ''

    let recorder: MediaRecorder

    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    } catch (error) {
      stream.getTracks().forEach(track => track.stop())
      throw micError(error)
    }

    chunksRef.current = []
    streamRef.current = stream
    recorderRef.current = recorder
    heardSpeechRef.current = false
    speechStartedAtRef.current = null
    speechDipStartedAtRef.current = null
    noiseFloorRef.current = 0.015
    silenceTriggeredRef.current = false
    silenceStartedAtRef.current = null
    startedAtRef.current = Date.now()

    stream.getAudioTracks().forEach(track => {
      track.addEventListener(
        'ended',
        () => {
          if (recorderRef.current === recorder && recorder.state !== 'inactive') {
            options.onError?.(new Error('Microphone disconnected during recording.'))
            recorder.stop()
          }
        },
        { once: true }
      )
    })

    recorder.ondataavailable = event => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data)
      }
    }

    recorder.onstop = () => {
      const chunks = chunksRef.current
      const recordingType = recorder.mimeType || mimeType || 'audio/webm'
      const durationMs = Date.now() - startedAtRef.current
      const heardSpeech = heardSpeechRef.current

      chunksRef.current = []
      cleanup()

      const resolver = stopResolverRef.current
      stopResolverRef.current = null

      if (!chunks.length) {
        resolver?.(null)

        return
      }

      resolver?.({
        audio: new Blob(chunks, { type: recordingType }),
        durationMs,
        heardSpeech
      })
    }

    recorder.onerror = event => {
      const error = micError((event as Event & { error?: unknown }).error)
      const resolver = stopResolverRef.current
      stopResolverRef.current = null
      cleanup()
      options.onError?.(error)
      resolver?.(null)
    }

    recorder.start()
    setRecording(true)
    startMeter(stream, options)
  }

  const stop: MicRecorderHandle['stop'] = () =>
    new Promise<MicRecording | null>(resolve => {
      const recorder = recorderRef.current

      if (!recorder || recorder.state === 'inactive') {
        cleanup()
        resolve(null)

        return
      }

      stopResolverRef.current = resolve
      recorder.stop()
    })

  const cancel: MicRecorderHandle['cancel'] = () => {
    const recorder = recorderRef.current
    const resolver = stopResolverRef.current
    stopResolverRef.current = null

    if (recorder && recorder.state !== 'inactive') {
      recorder.ondataavailable = null
      recorder.onerror = null
      recorder.onstop = null
      recorder.stop()
    }

    cleanup()
    resolver?.(null)
  }

  const handle: MicRecorderHandle = { start, stop, cancel }

  return { handle, level, recording }
}
