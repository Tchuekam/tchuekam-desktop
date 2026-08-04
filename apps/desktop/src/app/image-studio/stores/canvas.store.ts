/**
 * TchueKAM Image Studio v2 — Canvas Store
 */

import { atom } from 'nanostores'
import { DEFAULT_BRUSH_CONFIG } from '../core/constants'
import type { BrushConfig, CanvasToolType, Point } from '../core/types'

export const $canvasZoom = atom<number>(1.0)
export const $canvasPan = atom<Point>({ x: 0, y: 0 })
export const $activeTool = atom<CanvasToolType>('brush')
export const $brushConfig = atom<BrushConfig>(DEFAULT_BRUSH_CONFIG)
export const $showGrid = atom<boolean>(false)
export const $snapGuides = atom<boolean>(true)

export function setCanvasZoom(zoom: number) {
  $canvasZoom.set(Math.max(0.3, Math.min(3.0, zoom)))
}

export function setCanvasPan(pan: Point) {
  $canvasPan.set(pan)
}

export function setActiveTool(tool: CanvasToolType) {
  $activeTool.set(tool)
}

export function updateBrushConfig(updater: (prev: BrushConfig) => BrushConfig) {
  $brushConfig.set(updater($brushConfig.get()))
}

export function setBrushSize(size: number) {
  updateBrushConfig(prev => ({ ...prev, size }))
}

export function setBrushColor(color: string) {
  updateBrushConfig(prev => ({ ...prev, color }))
}

export function toggleGrid() {
  $showGrid.set(!$showGrid.get())
}
