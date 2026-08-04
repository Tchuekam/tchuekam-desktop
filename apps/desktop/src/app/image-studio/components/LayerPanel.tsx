/**
 * TchueKAM Image Studio v2 — LayerPanel Component
 */

import { IconCopyleft, IconEye, IconPlus, IconTrash } from '@tabler/icons-react'
import React from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { createEmptyLayer } from '../core/models'
import { useLayers } from '../hooks/useLayers'
import { showToast } from '../stores/ui.store'

export const LayerPanel: React.FC = () => {
  const {
    layers,
    activeLayerId,
    setActiveLayerId,
    createLayer,
    deleteLayer,
    duplicateLayer,
    reorderLayers,
    setLayerOpacity,
    toggleLayerVisibility
  } = useLayers()

  const handleImageUploadToCanvas = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = event => {
      const img = new Image()
      img.onload = () => {
        const layer = createEmptyLayer(file.name.split('.')[0] || 'Image Layer', 'image')
        layer.imageUrl = event.target?.result as string
        layer.dataUrl = event.target?.result as string
        createLayer(layer.name, 'image')
        showToast('Image added as a new layer')
      }
      img.src = event.target?.result as string
    }
    reader.readAsDataURL(file)
  }

  return (
    <div className="flex w-64 shrink-0 flex-col border-l border-white/8 bg-[#0D0E15]">
      <div className="flex items-center justify-between p-3 border-b border-white/8">
        <span className="text-[0.6875rem] font-bold uppercase tracking-wider text-white/50">Layers</span>
        <div className="flex gap-1.5">
          <label className="grid size-7 place-items-center rounded-lg border border-white/8 bg-white/5 text-white/60 hover:bg-white/10 hover:text-white cursor-pointer">
            <input accept="image/*" className="hidden" onChange={handleImageUploadToCanvas} type="file" />
            <IconPlus size="0.95rem" />
          </label>
          <button
            className="grid size-7 place-items-center rounded-lg border border-white/8 bg-white/5 text-white/60 hover:bg-white/10 hover:text-white"
            onClick={() => createLayer('New Layer', 'paint')}
            title="New Empty Layer"
          >
            <IconPlus size="0.95rem" />
          </button>
        </div>
      </div>

      <ScrollArea className="flex-1 p-2">
        <div className="flex flex-col gap-1.5">
          {layers.map((layer, index) => (
            <div
              className={cn(
                'flex flex-col gap-2 rounded-xl border p-2.5 transition duration-150',
                activeLayerId === layer.id
                  ? 'border-[#8b46ff] bg-[#8b46ff]/10 text-white'
                  : 'border-white/8 bg-white/3 hover:bg-white/5'
              )}
              key={layer.id}
              onClick={() => setActiveLayerId(layer.id)}
            >
              <div className="flex items-center gap-2">
                <button
                  className="text-white/60 hover:text-white"
                  onClick={e => {
                    e.stopPropagation()
                    toggleLayerVisibility(layer.id)
                  }}
                >
                  <IconEye className={layer.visible ? 'text-[#8b46ff]' : 'text-white/20'} size="0.95rem" />
                </button>
                <span className="truncate text-xs font-bold">{layer.name}</span>
                <div className="ml-auto flex items-center gap-1.5">
                  <button
                    className="text-white/40 hover:text-white"
                    onClick={e => {
                      e.stopPropagation()
                      reorderLayers(index, index - 1)
                    }}
                  >
                    ▲
                  </button>
                  <button
                    className="text-white/40 hover:text-white"
                    onClick={e => {
                      e.stopPropagation()
                      reorderLayers(index, index + 1)
                    }}
                  >
                    ▼
                  </button>
                  <button
                    className="text-white/40 hover:text-white"
                    onClick={e => {
                      e.stopPropagation()
                      duplicateLayer(layer.id)
                    }}
                    title="Duplicate Layer"
                  >
                    <IconCopyleft size="0.85rem" />
                  </button>
                  <button
                    className="text-red-400/60 hover:text-red-400"
                    onClick={e => {
                      e.stopPropagation()
                      deleteLayer(layer.id)
                    }}
                  >
                    <IconTrash size="0.85rem" />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-2 text-[0.625rem] text-white/50">
                <span>Opacity:</span>
                <input
                  className="flex-1 accent-[#8b46ff]"
                  max="1"
                  min="0"
                  onChange={e => setLayerOpacity(layer.id, parseFloat(e.target.value), layer.opacity)}
                  step="0.05"
                  type="range"
                  value={layer.opacity}
                />
                <span className="w-6 text-right font-bold text-white">{Math.round(layer.opacity * 100)}%</span>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
