/**
 * TchueKAM Image Studio v2 — UI Store
 */

import { atom } from 'nanostores'
import type { StudioTab } from '../core/types'

export interface ToastMessage {
  id: string
  message: string
  type: 'success' | 'error' | 'info'
}

export const $activeTab = atom<StudioTab>('canvas')
export const $toastMessage = atom<ToastMessage | null>(null)

export function setActiveTab(tab: StudioTab) {
  $activeTab.set(tab)
}

export function showToast(message: string, type: 'success' | 'error' | 'info' = 'success') {
  const toast: ToastMessage = {
    id: `toast-${Date.now()}`,
    message,
    type
  }
  $toastMessage.set(toast)

  setTimeout(() => {
    if ($toastMessage.get()?.id === toast.id) {
      $toastMessage.set(null)
    }
  }, 3000)
}
