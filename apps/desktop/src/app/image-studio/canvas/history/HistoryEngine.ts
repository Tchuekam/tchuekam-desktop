/**
 * TchueKAM Image Studio v2 — Canvas Pixel Snapshot History Engine
 */

import type { CanvasLayerState } from '../../core/types'
import { $layers, setLayers } from '../../stores/layer.store'
import { updateHistoryStatus } from '../../stores/history.store'

export class HistoryEngine {
  private undoStack: string[] = []
  private redoStack: string[] = []
  private maxStack: number = 30

  public pushSnapshot(): void {
    const layers = $layers.get()
    const serialized = JSON.stringify(
      layers.map(l => ({
        id: l.id,
        name: l.name,
        visible: l.visible,
        opacity: l.opacity,
        type: l.type,
        x: l.x,
        y: l.y,
        width: l.width,
        height: l.height,
        dataUrl: l.dataUrl
      }))
    )

    this.undoStack.push(serialized)
    if (this.undoStack.length > this.maxStack) {
      this.undoStack.shift()
    }
    this.redoStack = []
    this.syncStores()
  }

  public undo(): boolean {
    if (this.undoStack.length === 0) return false

    const currentState = JSON.stringify($layers.get())
    this.redoStack.push(currentState)

    const stateStr = this.undoStack.pop()!
    const parsed = JSON.parse(stateStr) as CanvasLayerState[]
    setLayers(parsed)
    this.syncStores()
    return true
  }

  public redo(): boolean {
    if (this.redoStack.length === 0) return false

    const currentState = JSON.stringify($layers.get())
    this.undoStack.push(currentState)

    const stateStr = this.redoStack.pop()!
    const parsed = JSON.parse(stateStr) as CanvasLayerState[]
    setLayers(parsed)
    this.syncStores()
    return true
  }

  public clear(): void {
    this.undoStack = []
    this.redoStack = []
    this.syncStores()
  }

  private syncStores(): void {
    updateHistoryStatus(this.undoStack.length, this.redoStack.length)
  }
}

export const historyEngine = new HistoryEngine()
