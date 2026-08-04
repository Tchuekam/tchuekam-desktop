/**
 * TchueKAM Image Studio v2 — CanvasViewport Component
 */

import React, { useCallback, useEffect, useRef } from 'react'
import { brushEngine } from '../canvas/tools/BrushEngine'
import { canvasRenderer } from '../canvas/renderer/CanvasRenderer'
import { historyEngine } from '../canvas/history/HistoryEngine'
import { useCanvas } from '../hooks/useCanvas'
import { useLayers } from '../hooks/useLayers'

export const CanvasViewport: React.FC = () => {
  const { zoom, pan, setPan, activeTool, brushConfig, showGrid } = useCanvas()
  const { layers, activeLayer } = useLayers()

  const mainCanvasRef = useRef<HTMLCanvasElement>(null)
  const isDrawingRef = useRef(false)
  const lastPosRef = useRef({ x: 0, y: 0 })
  const isPanningRef = useRef(false)
  const panStartRef = useRef({ x: 0, y: 0 })

  const drawMainCanvas = useCallback(() => {
    const mainCanvas = mainCanvasRef.current
    if (!mainCanvas) return
    const ctx = mainCanvas.getContext('2d')
    if (!ctx) return

    canvasRenderer.render(ctx, layers, showGrid, 800, 600)
  }, [layers, showGrid])

  useEffect(() => {
    drawMainCanvas()
  }, [drawMainCanvas])

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const mainCanvas = mainCanvasRef.current
    if (!mainCanvas || !activeLayer || activeTool === 'select' || activeTool === 'pan') return

    const rect = mainCanvas.getBoundingClientRect()
    const clientX = (e.clientX - rect.left) / zoom
    const clientY = (e.clientY - rect.top) / zoom

    historyEngine.pushSnapshot()
    isDrawingRef.current = true
    lastPosRef.current = { x: clientX - activeLayer.x, y: clientY - activeLayer.y }
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const mainCanvas = mainCanvasRef.current
    if (!mainCanvas || !activeLayer || !isDrawingRef.current) return

    const ctx = mainCanvas.getContext('2d')
    if (!ctx) return

    const rect = mainCanvas.getBoundingClientRect()
    const clientX = (e.clientX - rect.left) / zoom
    const clientY = (e.clientY - rect.top) / zoom
    const currentPos = { x: clientX - activeLayer.x, y: clientY - activeLayer.y }

    brushEngine.drawStroke(ctx, lastPosRef.current, currentPos, activeTool, brushConfig)
    lastPosRef.current = currentPos
    drawMainCanvas()
  }

  const handleMouseUp = () => {
    isDrawingRef.current = false
  }

  const handleContainerMouseDown = (e: React.MouseEvent) => {
    if (activeTool === 'pan' || e.button === 1 || (e.button === 0 && e.shiftKey)) {
      isPanningRef.current = true
      panStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }
    }
  }

  const handleContainerMouseMove = (e: React.MouseEvent) => {
    if (isPanningRef.current) {
      setPan({
        x: e.clientX - panStartRef.current.x,
        y: e.clientY - panStartRef.current.y
      })
    }
  }

  const handleContainerMouseUp = () => {
    isPanningRef.current = false
  }

  return (
    <div
      className="relative flex-1 cursor-crosshair overflow-hidden bg-[#07080b]"
      onMouseDown={handleContainerMouseDown}
      onMouseMove={handleContainerMouseMove}
      onMouseUp={handleContainerMouseUp}
      style={{
        backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.03) 1px, transparent 1px)',
        backgroundSize: '20px 20px'
      }}
    >
      <div
        className="absolute"
        style={{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: '0 0',
          left: 'calc(50% - 400px)',
          top: 'calc(50% - 300px)',
          width: '800px',
          height: '600px'
        }}
      >
        <canvas
          className="shadow-2xl border border-white/8"
          height={600}
          onMouseDown={handleMouseDown}
          onMouseLeave={handleMouseUp}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          ref={mainCanvasRef}
          width={800}
        />
      </div>
    </div>
  )
}
