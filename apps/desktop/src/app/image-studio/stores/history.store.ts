/**
 * TchueKAM Image Studio v2 — History Store
 */

import { atom } from 'nanostores'

export const $canUndo = atom<boolean>(false)
export const $canRedo = atom<boolean>(false)
export const $undoCount = atom<number>(0)
export const $redoCount = atom<number>(0)

export function updateHistoryStatus(undoCount: number, redoCount: number) {
  $undoCount.set(undoCount)
  $redoCount.set(redoCount)
  $canUndo.set(undoCount > 0)
  $canRedo.set(redoCount > 0)
}
