/**
 * TchueKAM Image Studio v2 — Selection Store
 */

import { atom } from 'nanostores'
import type { Rect } from '../core/types'

export const $selectionBounds = atom<Rect | null>(null)
export const $selectedLayerIds = atom<string[]>([])

export function setSelectionBounds(bounds: Rect | null) {
  $selectionBounds.set(bounds)
}

export function setSelectedLayerIds(ids: string[]) {
  $selectedLayerIds.set(ids)
}

export function clearSelection() {
  $selectionBounds.set(null)
  $selectedLayerIds.set([])
}
