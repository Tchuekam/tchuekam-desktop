/**
 * TchueKAM Image Studio v2 — Canvas Composite Renderer
 */

import type { CanvasLayerState } from '../../core/types'

export class CanvasRenderer {
  public render(
    targetCtx: CanvasContext2D | CanvasRenderingContext2D,
    layers: CanvasLayerState[],
    showGrid: boolean = false,
    width: number = 800,
    height: number = 600
  ): void {
    targetCtx.clearRect(0, 0, width, height)

    // Render layers from bottom to top (reversed index array)
    for (let i = layers.length - 1; i >= 0; i--) {
      const layer = layers[i]

      if (layer.visible && layer.opacity > 0) {
        targetCtx.globalAlpha = layer.opacity

        if (layer.dataUrl) {
          const img = new Image()
          img.src = layer.dataUrl
          targetCtx.drawImage(img, layer.x, layer.y, layer.width, layer.height)
        }
      }
    }

    targetCtx.globalAlpha = 1.0

    // Render Grid Overlay
    if (showGrid) {
      targetCtx.strokeStyle = 'rgba(255, 255, 255, 0.08)'
      targetCtx.lineWidth = 1
      const size = 40

      for (let x = 0; x < width; x += size) {
        targetCtx.beginPath()
        targetCtx.moveTo(x, 0)
        targetCtx.lineTo(x, height)
        targetCtx.stroke()
      }

      for (let y = 0; y < height; y += size) {
        targetCtx.beginPath()
        targetCtx.moveTo(0, y)
        targetCtx.lineTo(width, y)
        targetCtx.stroke()
      }
    }
  }
}

type CanvasContext2D = CanvasRenderingContext2D

export const canvasRenderer = new CanvasRenderer()
