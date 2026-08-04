/**
 * TchueKAM Image Studio v2 — MockupTab Component
 */

import { IconDeviceLaptop } from '@tabler/icons-react'
import React from 'react'
import { MOCKUP_TYPES } from '../core/constants'
import { generateProductMockup } from '../mockups/builder'

export const MockupTab: React.FC = () => {
  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
      <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">Mockups Maker</h3>
        <p className="text-[0.6875rem] text-white/40">Project your active drawing layer directly onto realistic mockups.</p>

        <div className="flex flex-col gap-2">
          {MOCKUP_TYPES.map(mock => (
            <button
              className="flex w-full items-center justify-between rounded-xl border border-white/8 bg-black/20 px-4 py-3 text-left transition hover:border-[#8b46ff]/50 hover:bg-[#8b46ff]/5"
              key={mock.id}
              onClick={() => generateProductMockup(mock.label)}
            >
              <span className="text-xs font-bold text-white">{mock.label}</span>
              <IconDeviceLaptop className="text-[#8b46ff]" size="0.95rem" />
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col justify-center items-center border border-white/8 rounded-2xl bg-black/40">
        <span className="text-xs text-white/30">Select an item to construct realistic product previews.</span>
      </div>
    </div>
  )
}
