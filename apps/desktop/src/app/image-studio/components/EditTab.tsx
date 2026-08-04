/**
 * TchueKAM Image Studio v2 — EditTab Component
 */

import React from 'react'
import { EDIT_OPERATIONS } from '../core/constants'
import type { EditOperationType } from '../core/types'
import { editingService } from '../application/services/EditingService'
import { useLayers } from '../hooks/useLayers'

export const EditTab: React.FC = () => {
  const { activeLayer } = useLayers()

  const handleEdit = (op: EditOperationType) => {
    if (!activeLayer) return
    editingService.processEdit({
      image: activeLayer.dataUrl || '',
      operation: op
    })
  }

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
      <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">AI Photo Editing</h3>

        <div className="flex flex-col gap-2.5">
          {EDIT_OPERATIONS.map(op => (
            <button
              className="flex w-full flex-col gap-0.5 rounded-xl border border-white/8 bg-black/20 p-3 text-left transition hover:border-[#8b46ff]/50 hover:bg-[#8b46ff]/5"
              key={op.id}
              onClick={() => handleEdit(op.id)}
            >
              <span className="text-xs font-bold text-white">{op.label}</span>
              <span className="text-[0.625rem] text-white/40">{op.desc}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col gap-4">
        <h4 className="text-sm font-bold">Active Layer for Editing</h4>
        <div className="flex-1 flex items-center justify-center border border-white/8 rounded-2xl bg-black/40 overflow-hidden">
          {activeLayer?.dataUrl || activeLayer?.imageUrl ? (
            <img
              alt={activeLayer.name}
              className="max-h-full max-w-full object-contain"
              src={activeLayer.dataUrl || activeLayer.imageUrl}
            />
          ) : (
            <span className="text-xs text-white/30">Select an active image layer to apply AI editing</span>
          )}
        </div>
      </div>
    </div>
  )
}
