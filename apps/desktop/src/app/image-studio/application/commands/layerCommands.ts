/**
 * TchueKAM Image Studio v2 — Layer Commands
 */

import { createEmptyLayer } from '../../core/models'
import type { CanvasLayerState } from '../../core/types'
import {
  $activeLayerId,
  $layers,
  addLayer,
  reorderLayers,
  setLayers,
  updateLayer
} from '../../stores/layer.store'
import { eventBus } from '../events/EventBus'
import type { ICommand } from './CommandBus'

export class CreateLayerCommand implements ICommand<CanvasLayerState> {
  readonly name = 'CreateLayer'
  readonly supportsUndo = true
  private createdLayer: CanvasLayerState | null = null

  constructor(
    private layerName: string = 'New Layer',
    private layerType: CanvasLayerState['type'] = 'paint'
  ) {}

  validate(): boolean {
    return true
  }

  execute(): CanvasLayerState {
    const layer = createEmptyLayer(this.layerName, this.layerType)
    this.createdLayer = layer
    addLayer(layer)
    eventBus.emit('LayerCreated', { layerId: layer.id })
    return layer
  }

  undo(): void {
    if (!this.createdLayer) return
    const current = $layers.get()
    const filtered = current.filter(l => l.id !== this.createdLayer!.id)
    setLayers(filtered)
    if ($activeLayerId.get() === this.createdLayer.id) {
      $activeLayerId.set(filtered[0]?.id || null)
    }
  }
}

export class DeleteLayerCommand implements ICommand<boolean> {
  readonly name = 'DeleteLayer'
  readonly supportsUndo = true
  private deletedLayer: CanvasLayerState | null = null
  private deletedIndex: number = -1

  constructor(private layerId: string) {}

  validate(): boolean {
    const layers = $layers.get()
    return layers.length > 1 && layers.some(l => l.id === this.layerId)
  }

  execute(): boolean {
    const layers = $layers.get()
    this.deletedIndex = layers.findIndex(l => l.id === this.layerId)
    if (this.deletedIndex === -1) return false

    this.deletedLayer = layers[this.deletedIndex]
    const updated = layers.filter(l => l.id !== this.layerId)
    setLayers(updated)

    if ($activeLayerId.get() === this.layerId) {
      $activeLayerId.set(updated[0]?.id || null)
    }

    eventBus.emit('LayerDeleted', { layerId: this.layerId })
    return true
  }

  undo(): void {
    if (!this.deletedLayer || this.deletedIndex === -1) return
    const layers = [...$layers.get()]
    layers.splice(this.deletedIndex, 0, this.deletedLayer)
    setLayers(layers)
    $activeLayerId.set(this.deletedLayer.id)
  }
}

export class DuplicateLayerCommand implements ICommand<CanvasLayerState | null> {
  readonly name = 'DuplicateLayer'
  readonly supportsUndo = true
  private duplicatedLayer: CanvasLayerState | null = null

  constructor(private layerId: string) {}

  validate(): boolean {
    return $layers.get().some(l => l.id === this.layerId)
  }

  execute(): CanvasLayerState | null {
    const original = $layers.get().find(l => l.id === this.layerId)
    if (!original) return null

    const copy: CanvasLayerState = {
      ...original,
      id: `layer-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
      name: `${original.name} Copy`
    }

    this.duplicatedLayer = copy
    addLayer(copy)
    eventBus.emit('LayerCreated', { layerId: copy.id })
    return copy
  }

  undo(): void {
    if (!this.duplicatedLayer) return
    const filtered = $layers.get().filter(l => l.id !== this.duplicatedLayer!.id)
    setLayers(filtered)
    if ($activeLayerId.get() === this.duplicatedLayer.id) {
      $activeLayerId.set(filtered[0]?.id || null)
    }
  }
}

export class ReorderLayersCommand implements ICommand<void> {
  readonly name = 'ReorderLayers'
  readonly supportsUndo = true

  constructor(
    private fromIndex: number,
    private toIndex: number
  ) {}

  validate(): boolean {
    const len = $layers.get().length
    return this.fromIndex >= 0 && this.fromIndex < len && this.toIndex >= 0 && this.toIndex < len
  }

  execute(): void {
    reorderLayers(this.fromIndex, this.toIndex)
    eventBus.emit('LayerReordered', { from: this.fromIndex, to: this.toIndex })
  }

  undo(): void {
    reorderLayers(this.toIndex, this.fromIndex)
    eventBus.emit('LayerReordered', { from: this.toIndex, to: this.fromIndex })
  }
}

export class UpdateLayerOpacityCommand implements ICommand<void> {
  readonly name = 'UpdateLayerOpacity'
  readonly supportsUndo = true

  constructor(
    private layerId: string,
    private newOpacity: number,
    private oldOpacity: number
  ) {}

  validate(): boolean {
    return $layers.get().some(l => l.id === this.layerId)
  }

  execute(): void {
    updateLayer(this.layerId, l => ({ ...l, opacity: this.newOpacity }))
  }

  undo(): void {
    updateLayer(this.layerId, l => ({ ...l, opacity: this.oldOpacity }))
  }
}

export class ToggleLayerVisibilityCommand implements ICommand<void> {
  readonly name = 'ToggleLayerVisibility'
  readonly supportsUndo = true

  constructor(private layerId: string) {}

  validate(): boolean {
    return $layers.get().some(l => l.id === this.layerId)
  }

  execute(): void {
    updateLayer(this.layerId, l => ({ ...l, visible: !l.visible }))
  }

  undo(): void {
    updateLayer(this.layerId, l => ({ ...l, visible: !l.visible }))
  }
}
