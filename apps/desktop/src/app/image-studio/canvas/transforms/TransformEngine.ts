/**
 * TchueKAM Image Studio v2 — Canvas Transform Engine
 */

import type { Point, Rect } from '../../core/types'

export class TransformEngine {
  public translatePoint(point: Point, pan: Point, zoom: number): Point {
    return {
      x: (point.x - pan.x) / zoom,
      y: (point.y - pan.y) / zoom
    }
  }

  public scaleRect(rect: Rect, scale: number): Rect {
    return {
      x: rect.x * scale,
      y: rect.y * scale,
      width: rect.width * scale,
      height: rect.height * scale
    }
  }
}

export const transformEngine = new TransformEngine()
