/**
 * TchueKAM Image Studio v2 — Brush & Mask Tool Engine
 */

import type { BrushConfig, CanvasToolType, Point } from '../../core/types'

export class BrushEngine {
  public drawStroke(
    ctx: CanvasRenderingContext2D,
    from: Point,
    to: Point,
    tool: CanvasToolType,
    config: BrushConfig
  ): void {
    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)

    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.globalAlpha = config.opacity
    ctx.lineWidth = config.size

    if (tool === 'brush') {
      ctx.strokeStyle = config.color
      ctx.globalCompositeOperation = 'source-over'
    } else if (tool === 'eraser') {
      ctx.strokeStyle = '#000000'
      ctx.globalCompositeOperation = 'destination-out'
    } else if (tool === 'mask') {
      ctx.strokeStyle = 'rgba(255, 0, 0, 0.4)'
      ctx.globalCompositeOperation = 'source-over'
    }

    ctx.stroke()
    ctx.globalCompositeOperation = 'source-over'
    ctx.globalAlpha = 1.0
  }
}

export const brushEngine = new BrushEngine()
