/**
 * TchueKAM Image Studio v2 — Layer Store
 */

import { atom } from 'nanostores'
import { createBaseBackgroundLayer } from '../core/models'
import type { CanvasLayerState } from '../core/types'

const initialBaseLayer = createBaseBackgroundLayer()

export const $layers = atom<CanvasLayerState[]>([initialBaseLayer])
export const $activeLayerId = atom<string | null>(initialBaseLayer.id)

export function setLayers(layers: CanvasLayerState[]) {
  $layers.set(layers)
}

export function setActiveLayerId(id: string | null) {
  $activeLayerId.set(id)
}

export function getActiveLayer(): CanvasLayerState | null {
  const activeId = $activeLayerId.get()
  const layers = $layers.get()
  return layers.find(l => l.id === activeId) || null
}

export function addLayer(layer: CanvasLayerState) {
  $layers.set([layer, ...$layers.get()])
  $activeLayerId.set(layer.id)
}

export function removeLayer(id: string) {
  const currentLayers = $layers.get()
  if (currentLayers.length <= 1) {
    return false
  }

  const updated = currentLayers.filter(l => l.id !== id)
  $layers.set(updated)

  if ($activeLayerId.get() === id) {
    $activeLayerId.set(updated[0]?.id || null)
  }
  return true
}

export function updateLayer(id: string, updater: (layer: CanvasLayerState) => CanvasLayerState) {
  $layers.set(
    $layers.get().map(l => (l.id === id ? updater(l) : l))
  )
}

export function reorderLayers(fromIndex: number, toIndex: number) {
  const current = [...$layers.get()]
  if (fromIndex < 0 || fromIndex >= current.length || toIndex < 0 || toIndex >= current.length) {
    return
  }
  const [moved] = current.splice(fromIndex, 1)
  current.splice(toIndex, 0, moved)
  $layers.set(current)
}
