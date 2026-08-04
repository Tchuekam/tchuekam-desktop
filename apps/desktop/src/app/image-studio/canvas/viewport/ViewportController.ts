/**
 * TchueKAM Image Studio v2 — Viewport Controller
 */

import type { Point } from '../../core/types'
import { $canvasPan, $canvasZoom, setCanvasPan, setCanvasZoom } from '../../stores/canvas.store'

export class ViewportController {
  public zoomIn(step: number = 0.1): void {
    setCanvasZoom($canvasZoom.get() + step)
  }

  public zoomOut(step: number = 0.1): void {
    setCanvasZoom($canvasZoom.get() - step)
  }

  public reset(): void {
    setCanvasZoom(1.0)
    setCanvasPan({ x: 0, y: 0 })
  }

  public panBy(delta: Point): void {
    const current = $canvasPan.get()
    setCanvasPan({
      x: current.x + delta.x,
      y: current.y + delta.y
    })
  }
}

export const viewportController = new ViewportController()
