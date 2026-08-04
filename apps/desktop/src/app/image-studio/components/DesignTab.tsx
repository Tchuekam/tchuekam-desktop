/**
 * TchueKAM Image Studio v2 — DesignTab Component
 */

import { IconPlayerPlay } from '@tabler/icons-react'
import React from 'react'
import { DESIGN_TEMPLATES } from '../core/constants'
import { generateDesignTemplate } from '../templates/generator'

export const DesignTab: React.FC = () => {
  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
      <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">Design Generator</h3>
        <p className="text-[0.6875rem] text-white/40">Select a template category to load layered designs onto your active canvas.</p>

        <div className="flex flex-col gap-2">
          {DESIGN_TEMPLATES.map(design => (
            <button
              className="flex w-full items-center justify-between rounded-xl border border-white/8 bg-black/20 px-4 py-3 text-left transition hover:border-[#8b46ff]/50 hover:bg-[#8b46ff]/5"
              key={design}
              onClick={() => generateDesignTemplate(design)}
            >
              <span className="text-xs font-bold text-white">{design}</span>
              <IconPlayerPlay className="text-[#8b46ff]" size="0.9rem" />
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col justify-center items-center border border-white/8 rounded-2xl bg-black/40">
        <span className="text-xs text-white/30">Templates output directly onto the Canvas Editor layer list</span>
      </div>
    </div>
  )
}
