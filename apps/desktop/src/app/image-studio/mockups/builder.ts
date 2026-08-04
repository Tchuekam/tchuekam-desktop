/**
 * TchueKAM Image Studio v2 — Product Mockup Builder Engine
 */

import { createEmptyLayer } from '../core/models'
import type { CanvasLayerState } from '../core/types'
import { getActiveLayer, addLayer } from '../stores/layer.store'
import { showToast } from '../stores/ui.store'

function base64Encode(str: string): string {
  return window.btoa(unescape(encodeURIComponent(str)))
}

export function generateProductMockup(productLabel: string): CanvasLayerState | null {
  const activeLayer = getActiveLayer()
  if (!activeLayer) {
    showToast('Select a layer to project onto mockup', 'error')
    return null
  }

  const layerData = activeLayer.dataUrl || ''
  const mockupSvg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" width="800" height="600">
      <rect width="100%" height="100%" fill="#161824" />
      <rect x="250" y="80" width="300" height="440" rx="30" fill="#2D3043" stroke="#4F526B" stroke-width="4" />
      <rect x="260" y="90" width="280" height="420" rx="20" fill="#0D0E15" />
      ${layerData ? `<image href="${layerData}" x="260" y="90" width="280" height="420" clip-path="inset(0px round 20px)" />` : ''}
      <text x="400" y="560" fill="white" font-family="system-ui, sans-serif" font-size="16" text-anchor="middle" font-weight="bold">${productLabel.toUpperCase()} MOCKUP</text>
    </svg>
  `

  const b64 = base64Encode(mockupSvg)
  const mockupUrl = `data:image/svg+xml;base64,${b64}`

  const mockLayer = createEmptyLayer(`${productLabel} Mockup`, 'image')
  mockLayer.imageUrl = mockupUrl
  mockLayer.dataUrl = mockupUrl
  addLayer(mockLayer)
  showToast('Mockup generated and loaded onto canvas')
  return mockLayer
}
