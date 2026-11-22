import { atom } from 'nanostores'

import {
  getIntelligenceStatus,
  installLocalIntelligenceModel,
  preloadLocalIntelligence,
  setIntelligenceMode
} from '@/hermes'
import type {
  IntelligenceMode,
  IntelligenceRouteEvent,
  IntelligenceStatusResponse
} from '@/types/hermes'

export const $intelligenceStatus = atom<IntelligenceStatusResponse | null>(null)
export const $intelligenceLoading = atom(false)
export const $intelligenceInstallingModel = atom<string | null>(null)
export const $activeMbowaRoute = atom<IntelligenceRouteEvent | null>(null)

let initializedListeners = false
let pollTimer: number | null = null

export async function refreshIntelligenceStatus(probe = true): Promise<IntelligenceStatusResponse | null> {
  $intelligenceLoading.set(true)

  try {
    const status = await getIntelligenceStatus(probe)
    $intelligenceStatus.set(status)

    return status
  } catch {
    // Keep existing snapshot if backend is still booting
    return $intelligenceStatus.get()
  } finally {
    $intelligenceLoading.set(false)
  }
}

export async function switchIntelligenceMode(mode: IntelligenceMode): Promise<IntelligenceStatusResponse | null> {
  $intelligenceLoading.set(true)

  try {
    const status = await setIntelligenceMode(mode, true)
    $intelligenceStatus.set(status)

    return status
  } finally {
    $intelligenceLoading.set(false)
  }
}

export async function preloadLocalModel(modelId = 'mbowagpt'): Promise<void> {
  $intelligenceInstallingModel.set(modelId)

  try {
    await preloadLocalIntelligence(modelId)
    await refreshIntelligenceStatus(false)
  } finally {
    $intelligenceInstallingModel.set(null)
  }
}

export async function installLocalModel(modelId: string): Promise<void> {
  $intelligenceInstallingModel.set(modelId)

  try {
    await installLocalIntelligenceModel(modelId)
    await refreshIntelligenceStatus(false)
  } finally {
    $intelligenceInstallingModel.set(null)
  }
}

export function applyIntelligenceRouteEvent(route: IntelligenceRouteEvent): void {
  $activeMbowaRoute.set(route)
  const prev = $intelligenceStatus.get()

  if (prev && typeof route.offline === 'boolean') {
    $intelligenceStatus.set({
      ...prev,
      active_tier: route.tier ?? (route.provider === 'mbowagpt' ? 'local' : 'cloud'),
      connectivity: route.offline ? 'offline' : prev.connectivity === 'offline' ? 'online' : prev.connectivity,
      offline: route.offline,
      online: !route.offline
    })
  }
}

export function applyConnectivitySnapshot(snapshot: Partial<IntelligenceStatusResponse>): void {
  const prev = $intelligenceStatus.get()

  if (!prev) {
    void refreshIntelligenceStatus(false)

    return
  }

  $intelligenceStatus.set({ ...prev, ...snapshot })
}

export function initIntelligenceListeners(): () => void {
  if (initializedListeners) {
    return () => {}
  }

  initializedListeners = true

  const onNetworkChange = () => {
    void refreshIntelligenceStatus(true)
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('online', onNetworkChange)
    window.addEventListener('offline', onNetworkChange)
    pollTimer = window.setInterval(() => {
      void refreshIntelligenceStatus(false)
    }, 30_000)
  }

  void refreshIntelligenceStatus(true)

  return () => {
    initializedListeners = false

    if (typeof window !== 'undefined') {
      window.removeEventListener('online', onNetworkChange)
      window.removeEventListener('offline', onNetworkChange)

      if (pollTimer !== null) {
        window.clearInterval(pollTimer)
        pollTimer = null
      }
    }
  }
}
