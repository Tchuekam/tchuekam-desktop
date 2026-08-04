/**
 * TchueKAM Image Studio v2 — PromptsTab Component
 */

import { IconTemplate } from '@tabler/icons-react'
import { useStore } from '@nanostores/react'
import React, { useEffect } from 'react'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { getStudioPrompts } from '../../../hermes'
import type { PromptVariable } from '../core/types'
import { $savedPrompts, setSavedPrompts } from '../stores/asset.store'

import {
  setPromptStyle,
  setPromptText
} from '../stores/generation.store'
import { setActiveTab, showToast } from '../stores/ui.store'

export const PromptsTab: React.FC = () => {
  const savedPrompts = useStore($savedPrompts)
  const [promptVars, setPromptVars] = React.useState<PromptVariable[]>([
    { name: 'subject', value: 'Ankara model' },
    { name: 'lighting', value: 'golden hour sunset' },
    { name: 'setting', value: 'Douala streets' }
  ])

  useEffect(() => {
    getStudioPrompts().then(res => {
      if (res.success) {
        setSavedPrompts(res.prompts)
      }
    })
  }, [])

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
      <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
        <span className="text-xs font-bold uppercase tracking-wider text-white/50">Prompt Variables</span>

        <div className="flex flex-col gap-3">
          {promptVars.map((v, i) => (
            <div className="flex flex-col gap-1" key={v.name}>
              <label className="text-[0.6875rem] font-semibold text-white/40">{`{${v.name}}`}</label>
              <Input
                className="h-8 text-xs rounded-lg border border-white/8 bg-black/40"
                onChange={e => {
                  const next = [...promptVars]
                  next[i].value = e.target.value
                  setPromptVars(next)
                }}
                value={v.value}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col gap-4">
        <span className="text-sm font-bold">Saved Prompts History</span>

        <ScrollArea className="flex-1 border border-white/8 rounded-2xl bg-black/40 p-4">
          {savedPrompts.length === 0 ? (
            <div className="size-full flex flex-col items-center justify-center text-white/30 text-xs">
              No saved prompts found.
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {savedPrompts.map(p => (
                <div
                  className="flex items-center justify-between border border-white/8 bg-black/20 rounded-xl p-3.5 hover:border-white/16 cursor-pointer"
                  key={p.id}
                  onClick={() => {
                    setPromptText(p.prompt)
                    setPromptStyle(p.style)
                    setActiveTab('generate')
                    showToast('Loaded prompt template')
                  }}
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="text-xs font-bold text-white leading-normal">{p.prompt}</span>
                    <span className="text-[0.625rem] text-white/40">{p.style.toUpperCase()}</span>
                  </div>
                  <IconTemplate className="text-[#8b46ff]" size="0.95rem" />
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  )
}
