/**
 * TchueKAM Image Studio v2 — Layer Manager Subsystem
 */

import type { CanvasLayerState } from '../../core/types'
import { $layers, addLayer, removeLayer, reorderLayers, updateLayer } from '../../stores/layer.store'

export class LayerManager {
  public getLayers(): CanvasLayerState[] {
    return $layers.get()
  }

  public create(layer: CanvasLayerState): void {
    addLayer(layer)
  }

  public delete(id: string): boolean {
    return removeLayer(id)
  }

  public reorder(from: number, to: number): void {
    reorderLayers(from, to)
  }

  public setOpacity(id: string, opacity: number): void {
    updateLayer(id, l => ({ ...l, opacity: Math.max(0, Math.min(1, opacity)) }))
  }

  public setVisibility(id: string, visible: boolean): void {
    updateLayer(id, l => ({ ...l, visible }))
  }
}

export const layerManager = new LayerManager()
