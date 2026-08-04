/**
 * TchueKAM Image Studio v2 — Selection Engine
 */

import type { Point, Rect } from '../../core/types'
import { $selectionBounds, clearSelection, setSelectionBounds } from '../../stores/selection.store'

export class SelectionEngine {
  public selectBounds(rect: Rect): void {
    setSelectionBounds(rect)
  }

  public clear(): void {
    clearSelection()
  }

  public isPointInside(point: Point): boolean {
    const bounds = $selectionBounds.get()
    if (!bounds) return false
    return (
      point.x >= bounds.x &&
      point.x <= bounds.x + bounds.width &&
      point.y >= bounds.y &&
      point.y <= bounds.y + bounds.height
    )
  }
}

export const selectionEngine = new SelectionEngine()
