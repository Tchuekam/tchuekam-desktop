/**
 * TchueKAM Image Studio v2 — useCanvas Hook
 */

import { useStore } from '@nanostores/react'
import {
  $activeTool,
  $brushConfig,
  $canvasPan,
  $canvasZoom,
  $showGrid,
  setActiveTool,
  setBrushColor,
  setBrushSize,
  setCanvasPan,
  setCanvasZoom,
  toggleGrid
} from '../stores/canvas.store'
import { $canRedo, $canUndo } from '../stores/history.store'
import { commandBus } from '../application/commands/CommandBus'
import { historyEngine } from '../canvas/history/HistoryEngine'

export function useCanvas() {
  const zoom = useStore($canvasZoom)
  const pan = useStore($canvasPan)
  const activeTool = useStore($activeTool)
  const brushConfig = useStore($brushConfig)
  const showGrid = useStore($showGrid)
  const canUndo = useStore($canUndo)
  const canRedo = useStore($canRedo)

  return {
    zoom,
    pan,
    activeTool,
    brushConfig,
    showGrid,
    canUndo,
    canRedo,
    setZoom: setCanvasZoom,
    setPan: setCanvasPan,
    setActiveTool,
    setBrushSize,
    setBrushColor,
    toggleGrid,
    undo: () => commandBus.undo() || historyEngine.undo(),
    redo: () => commandBus.redo() || historyEngine.redo(),
    resetView: () => {
      setCanvasZoom(1.0)
      setCanvasPan({ x: 0, y: 0 })
    }
  }
}
