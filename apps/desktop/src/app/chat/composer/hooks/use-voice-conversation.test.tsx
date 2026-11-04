// @vitest-environment node
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { JSDOM } from 'jsdom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { sanitizeTextForSpeech } from '@/lib/speech-text'

import { useVoiceConversation } from './use-voice-conversation'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/'
})

Object.defineProperty(globalThis, 'window', {
  configurable: true,
  value: dom.window,
  writable: true
})
Object.defineProperty(globalThis, 'document', {
  configurable: true,
  value: dom.window.document,
  writable: true
})
Object.defineProperty(globalThis, 'navigator', {
  configurable: true,
  value: dom.window.navigator,
  writable: true
})
Object.defineProperty(globalThis, 'HTMLElement', {
  configurable: true,
  value: dom.window.HTMLElement,
  writable: true
})
Object.defineProperty(globalThis, 'KeyboardEvent', {
  configurable: true,
  value: dom.window.KeyboardEvent,
  writable: true
})
;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

const {
  mockCancel,
  mockNotify,
  mockNotifyError,
  mockPlaySpeechText,
  mockPrefetchSpeechText,
  mockStart,
  mockStop,
  mockStopVoicePlayback,
  mockWasVoicePlaybackStopped
} = vi.hoisted(() => ({
  mockCancel: vi.fn(),
  mockNotify: vi.fn(),
  mockNotifyError: vi.fn(),
  mockPlaySpeechText: vi.fn(),
  mockPrefetchSpeechText: vi.fn(),
  mockStart: vi.fn(),
  mockStop: vi.fn(),
  mockStopVoicePlayback: vi.fn(),
  mockWasVoicePlaybackStopped: vi.fn(() => false)
}))

let latestStartOptions: {
  onError?: (error: Error) => void
  onSilence?: () => void
} | null = null

vi.mock('./use-mic-recorder', () => ({
  useMicRecorder: () => ({
    handle: {
      cancel: mockCancel,
      start: mockStart.mockImplementation(async options => {
        latestStartOptions = options ?? null
      }),
      stop: mockStop
    },
    level: 0.25,
    recording: true
  })
}))

vi.mock('@/lib/voice-playback', () => ({
  playSpeechText: mockPlaySpeechText,
  prefetchSpeechText: mockPrefetchSpeechText,
  stopVoicePlayback: mockStopVoicePlayback,
  wasVoicePlaybackStopped: mockWasVoicePlaybackStopped
}))

vi.mock('@/store/notifications', () => ({
  notify: mockNotify,
  notifyError: mockNotifyError
}))

describe('useVoiceConversation enterprise lifecycle', () => {
  beforeEach(() => {
    latestStartOptions = null
    mockStart.mockClear()
    mockStop.mockReset()
    mockCancel.mockClear()
    mockPlaySpeechText.mockReset()
    mockPrefetchSpeechText.mockClear()
    mockStopVoicePlayback.mockClear()
    mockWasVoicePlaybackStopped.mockReset()
    mockWasVoicePlaybackStopped.mockReturnValue(false)
    mockNotify.mockClear()
    mockNotifyError.mockClear()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllTimers()
  })

  it('sanitizes markdown and code blocks for speech synthesis', () => {
    expect(sanitizeTextForSpeech('Hello **world**! `code` here.')).toContain('Hello world')
  })

  it('ignores recordings where sustained speech was not confirmed (heardSpeech === false) and re-arms listening', async () => {
    const onSubmit = vi.fn()
    const onTranscribeAudio = vi.fn()
    const consumePendingResponse = vi.fn()

    mockStop.mockResolvedValue({
      audio: new Blob(['silence'], { type: 'audio/webm' }),
      durationMs: 400,
      heardSpeech: false
    })

    const { result } = renderHook(() =>
      useVoiceConversation({
        busy: false,
        consumePendingResponse,
        enabled: true,
        onSubmit,
        onTranscribeAudio,
        pendingResponse: () => null
      })
    )

    await waitFor(() => expect(result.current.status).toBe('listening'))
    expect(mockStart).toHaveBeenCalledTimes(1)

    await act(async () => {
      latestStartOptions?.onSilence?.()
    })

    expect(onTranscribeAudio).not.toHaveBeenCalled()
    expect(onSubmit).not.toHaveBeenCalled()
    await waitFor(() => expect(result.current.status).toBe('listening'))
    expect(mockStart).toHaveBeenCalledTimes(2)
  })

  it('filters empty/hallucinated transcripts without entering thinking state and resumes listening', async () => {
    const onSubmit = vi.fn()
    const onTranscribeAudio = vi.fn().mockResolvedValue('   ')
    const consumePendingResponse = vi.fn()

    mockStop.mockResolvedValue({
      audio: new Blob(['noise'], { type: 'audio/webm' }),
      durationMs: 900,
      heardSpeech: true
    })

    const { result } = renderHook(() =>
      useVoiceConversation({
        busy: false,
        consumePendingResponse,
        enabled: true,
        onSubmit,
        onTranscribeAudio,
        pendingResponse: () => null
      })
    )

    await waitFor(() => expect(result.current.status).toBe('listening'))

    await act(async () => {
      latestStartOptions?.onSilence?.()
    })

    expect(onTranscribeAudio).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
    await waitFor(() => expect(result.current.status).toBe('listening'))
  })

  it('recovers cleanly to listening if onSubmit rejects turn submission (e.g. busy guard returns false)', async () => {
    const onSubmit = vi.fn().mockResolvedValue(false)
    const onTranscribeAudio = vi.fn().mockResolvedValue('Hello Tchuekam')
    const consumePendingResponse = vi.fn()

    mockStop.mockResolvedValue({
      audio: new Blob(['speech'], { type: 'audio/webm' }),
      durationMs: 1200,
      heardSpeech: true
    })

    const { result } = renderHook(() =>
      useVoiceConversation({
        busy: false,
        consumePendingResponse,
        enabled: true,
        onSubmit,
        onTranscribeAudio,
        pendingResponse: () => null
      })
    )

    await waitFor(() => expect(result.current.status).toBe('listening'))

    await act(async () => {
      latestStartOptions?.onSilence?.()
    })

    expect(consumePendingResponse).toHaveBeenCalled()
    expect(onSubmit).toHaveBeenCalledWith('Hello Tchuekam')
    await waitFor(() => expect(result.current.status).toBe('listening'))
  })

  it('streams multi-sentence responses, prefetches sentence N+1, and only re-arms mic after all sentences finish', async () => {
    let busy = false
    let currentResponse: { id: string; pending: boolean; text: string } | null = null
    const onTranscribeAudio = vi.fn().mockResolvedValue('Explain the architecture')
    const consumePendingResponse = vi.fn()

    mockStop.mockResolvedValue({
      audio: new Blob(['speech'], { type: 'audio/webm' }),
      durationMs: 1500,
      heardSpeech: true
    })
    mockPlaySpeechText.mockResolvedValue(true)

    const onSubmit = vi.fn().mockImplementation(async () => {
      busy = true
      currentResponse = {
        id: 'assistant-msg-1',
        pending: false,
        text: 'First sentence is ready now. Second sentence follows right after.'
      }
      busy = false

      return true
    })

    const { rerender, result } = renderHook(() =>
      useVoiceConversation({
        busy,
        consumePendingResponse,
        enabled: true,
        onSubmit,
        onTranscribeAudio,
        pendingResponse: () => currentResponse
      })
    )

    await waitFor(() => expect(result.current.status).toBe('listening'))
    mockStart.mockClear()

    await act(async () => {
      latestStartOptions?.onSilence?.()
    })

    rerender()

    await waitFor(() => expect(mockPlaySpeechText).toHaveBeenCalledTimes(2))
    expect(mockPlaySpeechText).toHaveBeenNthCalledWith(1, 'First sentence is ready now.', {
      source: 'voice-conversation'
    })
    expect(mockPrefetchSpeechText).toHaveBeenCalledWith('Second sentence follows right after.')
    expect(mockPlaySpeechText).toHaveBeenNthCalledWith(2, 'Second sentence follows right after.', {
      source: 'voice-conversation'
    })

    await waitFor(() => expect(result.current.status).toBe('listening'))
    expect(mockStart).toHaveBeenCalledTimes(1)
  })

  it('flushes remaining buffered sentences and resumes listening when playback is stopped externally (barge-in)', async () => {
    let currentResponse: { id: string; pending: boolean; text: string } | null = null
    const onTranscribeAudio = vi.fn().mockResolvedValue('Give me a long answer')
    const consumePendingResponse = vi.fn()

    mockStop.mockResolvedValue({
      audio: new Blob(['speech'], { type: 'audio/webm' }),
      durationMs: 1400,
      heardSpeech: true
    })

    // Simulate user clicking Stop during the first sentence
    mockPlaySpeechText.mockResolvedValueOnce(false)
    mockWasVoicePlaybackStopped.mockReturnValue(true)

    const onSubmit = vi.fn().mockImplementation(async () => {
      currentResponse = {
        id: 'assistant-msg-2',
        pending: false,
        text: 'First sentence gets interrupted. Second sentence must never be spoken.'
      }

      return true
    })

    const { rerender, result } = renderHook(() =>
      useVoiceConversation({
        busy: false,
        consumePendingResponse,
        enabled: true,
        onSubmit,
        onTranscribeAudio,
        pendingResponse: () => currentResponse
      })
    )

    await waitFor(() => expect(result.current.status).toBe('listening'))

    await act(async () => {
      latestStartOptions?.onSilence?.()
    })

    rerender()

    await waitFor(() => expect(mockPlaySpeechText).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(result.current.status).toBe('listening'))
    // Second sentence was flushed on barge-in!
    expect(mockPlaySpeechText).toHaveBeenCalledTimes(1)
  })
})
