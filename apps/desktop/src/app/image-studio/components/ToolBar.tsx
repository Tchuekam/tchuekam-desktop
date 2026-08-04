/**
 * TchueKAM Image Studio v2 — ToolBar Component
 */

import {
  IconArrowBackUp,
  IconArrowForwardUp,
  IconBrush,
  IconDownload,
  IconEraser,
  IconGridPattern,
  IconHandGrab,
  IconRefresh,
  IconSquare,
  IconZoomIn,
  IconZoomOut
} from '@tabler/icons-react'
import React from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useCanvas } from '../hooks/useCanvas'
import { useLayers } from '../hooks/useLayers'
import { exporter } from '../export/exporter'

export const ToolBar: React.FC = () => {
  const {
    activeTool,
    setActiveTool,
    brushConfig,
    setBrushSize,
    setBrushColor,
    showGrid,
    toggleGrid,
    zoom,
    setZoom,
    resetView,
    undo,
    redo
  } = useCanvas()
  const { layers } = useLayers()

  return (
    <div className="flex h-12 items-center gap-2 border-b border-white/8 bg-[#0D0E15]/50 px-4">
      <div className="flex items-center gap-0.5 rounded-lg border border-white/8 bg-black/30 p-0.5">
        {[
          { id: 'brush', icon: IconBrush, label: 'Brush' },
          { id: 'eraser', icon: IconEraser, label: 'Eraser' },
          { id: 'mask', icon: IconSquare, label: 'Mask paint' },
          { id: 'pan', icon: IconHandGrab, label: 'Pan' }
        ].map(tool => (
          <button
            className={cn(
              'grid size-8 place-items-center rounded-md text-white/70 transition hover:text-white',
              activeTool === tool.id ? 'bg-white/10 text-white font-bold' : ''
            )}
            key={tool.id}
            onClick={() => setActiveTool(tool.id as any)}
            title={tool.label}
          >
            <tool.icon size="1.1rem" stroke={1.5} />
          </button>
        ))}
      </div>

      <div className="h-4 w-px bg-white/8" />

      {(activeTool === 'brush' || activeTool === 'eraser' || activeTool === 'mask') && (
        <div className="flex items-center gap-3 text-xs text-white/60">
          <span className="font-semibold">Size:</span>
          <input
            className="w-20 accent-[#8b46ff]"
            max="100"
            min="2"
            onChange={e => setBrushSize(parseInt(e.target.value))}
            type="range"
            value={brushConfig.size}
          />
          <span className="w-6 text-right font-bold text-white">{brushConfig.size}px</span>

          {activeTool === 'brush' && (
            <>
              <div className="h-4 w-px bg-white/8" />
              <span className="font-semibold">Color:</span>
              <input
                className="size-6 cursor-pointer border-0 bg-transparent"
                onChange={e => setBrushColor(e.target.value)}
                type="color"
                value={brushConfig.color}
              />
            </>
          )}
        </div>
      )}

      <div className="ml-auto flex items-center gap-2">
        <button
          className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
          onClick={undo}
          title="Undo"
        >
          <IconArrowBackUp size="1.1rem" />
        </button>
        <button
          className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
          onClick={redo}
          title="Redo"
        >
          <IconArrowForwardUp size="1.1rem" />
        </button>
        <button
          className={cn(
            'grid size-8 place-items-center rounded-lg border text-white/60 hover:text-white transition',
            showGrid ? 'border-white/20 bg-white/10 text-white' : 'border-white/8'
          )}
          onClick={toggleGrid}
          title="Toggle Grid"
        >
          <IconGridPattern size="1.1rem" />
        </button>
        <button
          className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
          onClick={() => setZoom(zoom + 0.1)}
          title="Zoom In"
        >
          <IconZoomIn size="1.1rem" />
        </button>
        <button
          className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
          onClick={() => setZoom(zoom - 0.1)}
          title="Zoom Out"
        >
          <IconZoomOut size="1.1rem" />
        </button>
        <button
          className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
          onClick={resetView}
          title="Reset View"
        >
          <IconRefresh size="1.1rem" />
        </button>
        <Button
          className="h-8 rounded-lg text-xs"
          onClick={() => exporter.exportCanvas(layers)}
          variant="secondary"
        >
          <IconDownload className="mr-1.5" size="0.95rem" /> Export
        </Button>
      </div>
    </div>
  )
}
