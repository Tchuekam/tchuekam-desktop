import { speakText } from '@/hermes'
import {
  $voicePlayback,
  setVoicePlaybackState,
  type VoicePlaybackSource,
  type VoicePlaybackState
} from '@/store/voice-playback'

import { sanitizeTextForSpeech } from './speech-text'

let currentAudio: HTMLAudioElement | null = null
let currentStop: (() => void) | null = null
let sequence = 0
let stoppedExternally = false
const MAX_PREFETCH_CACHE = 6
const speechCache = new Map<string, Promise<{ data_url: string }>>()

function currentState(
  status: VoicePlaybackState['status'],
  options?: VoicePlaybackOptions,
  audioElement: HTMLAudioElement | null = null
): VoicePlaybackState {
  return {
    audioElement,
    messageId: options?.messageId ?? null,
    sequence,
    source: options?.source ?? null,
    status
  }
}

export interface VoicePlaybackOptions {
  messageId?: string | null
  source: VoicePlaybackSource
}

function cleanupActiveAudio() {
  sequence += 1
  currentStop?.()
  currentStop = null

  if (currentAudio) {
    currentAudio.pause()
    currentAudio.src = ''
    currentAudio.load()
    currentAudio = null
  }
}

function fetchOrGetCachedSpeech(speakableText: string): Promise<{ data_url: string }> {
  const existing = speechCache.get(speakableText)

  if (existing) {
    speechCache.delete(speakableText)

    return existing
  }

  return speakText(speakableText)
}

export function prefetchSpeechText(text: string) {
  const speakableText = sanitizeTextForSpeech(text)

  if (!speakableText || speechCache.has(speakableText)) {
    return
  }

  if (speechCache.size >= MAX_PREFETCH_CACHE) {
    const oldestKey = speechCache.keys().next().value

    if (oldestKey !== undefined) {
      speechCache.delete(oldestKey)
    }
  }

  const pending = speakText(speakableText).catch(error => {
    speechCache.delete(speakableText)
    throw error
  })

  speechCache.set(speakableText, pending)
  void pending.catch(() => undefined)
}

export function stopVoicePlayback() {
  stoppedExternally = true
  speechCache.clear()
  cleanupActiveAudio()

  setVoicePlaybackState({
    audioElement: null,
    messageId: null,
    sequence,
    source: null,
    status: 'idle'
  })
}

export function wasVoicePlaybackStopped(): boolean {
  return stoppedExternally
}

export async function playSpeechText(text: string, options: VoicePlaybackOptions): Promise<boolean> {
  cleanupActiveAudio()
  stoppedExternally = false

  const speakableText = sanitizeTextForSpeech(text)

  if (!speakableText) {
    setVoicePlaybackState(currentState('idle'))

    return false
  }

  const ownSequence = sequence
  const isCurrent = () => ownSequence === sequence

  setVoicePlaybackState(currentState('preparing', options))

  try {
    const response = await fetchOrGetCachedSpeech(speakableText)

    if (!isCurrent()) {
      return false
    }

    const audio = new Audio(response.data_url)
    currentAudio = audio
    setVoicePlaybackState(currentState('speaking', options, audio))

    await new Promise<void>((resolve, reject) => {
      const cleanup = () => {
        audio.removeEventListener('ended', onEnded)
        audio.removeEventListener('error', onError)
        currentStop = null
      }

      const onEnded = () => {
        cleanup()
        resolve()
      }

      const onError = () => {
        cleanup()
        reject(new Error('Playback failed'))
      }

      currentStop = () => {
        cleanup()
        resolve()
      }

      audio.addEventListener('ended', onEnded, { once: true })
      audio.addEventListener('error', onError, { once: true })
      void audio.play().catch(reject)
    })

    if (!isCurrent()) {
      return false
    }

    currentAudio = null
    setVoicePlaybackState(currentState('idle'))

    return true
  } catch (error) {
    if (isCurrent()) {
      currentStop = null
      currentAudio = null
      setVoicePlaybackState(currentState('idle'))
    }

    throw error
  }
}

export function isVoicePlaybackActive() {
  return $voicePlayback.get().status !== 'idle'
}
