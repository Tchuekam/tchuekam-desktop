/**
 * TchueKAM Image Studio v2 — Graphics Template Builder Engine
 */

import { createEmptyLayer } from '../core/models'
import type { CanvasLayerState } from '../core/types'
import { addLayer } from '../stores/layer.store'
import { showToast } from '../stores/ui.store'

export function generateDesignTemplate(category: string): CanvasLayerState {
  const canvas = document.createElement('canvas')
  canvas.width = 800
  canvas.height = 600
  const ctx = canvas.getContext('2d')

  if (ctx) {
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, 800, 600)

    ctx.fillStyle = 'rgba(139, 70, 255, 0.4)'
    ctx.beginPath()
    ctx.arc(400, 300, 180, 0, Math.PI * 2)
    ctx.fill()

    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 36px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('DESIGN GENERATOR', 400, 260)

    ctx.fillStyle = '#94a3b8'
    ctx.font = '20px system-ui, sans-serif'
    ctx.fillText(category.toUpperCase(), 400, 310)
  }

  const layer = createEmptyLayer(`Design - ${category}`, 'paint')
  layer.dataUrl = canvas.toDataURL()
  addLayer(layer)
  showToast(`${category} template loaded on canvas`)
  return layer
}
