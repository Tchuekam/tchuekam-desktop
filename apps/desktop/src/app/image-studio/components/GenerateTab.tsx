/**
 * TchueKAM Image Studio v2 — GenerateTab Component
 */

import { IconSparkles } from '@tabler/icons-react'
import { useStore } from '@nanostores/react'
import React from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ASPECT_RATIOS, QUALITY_PRESETS, STYLE_PRESETS } from '../core/constants'
import type { AspectRatioType, QualityType } from '../core/types'
import { createEmptyLayer } from '../core/models'
import { generationService } from '../application/services/GenerationService'
import { useLayers } from '../hooks/useLayers'

import {
  $comparisonImage,
  $comparisonSliderVal,
  $generatedImages,
  $isGenerating,
  $promptAspectRatio,
  $promptModel,
  $promptQuality,
  $promptStyle,
  $promptText,
  setComparisonImage,
  setComparisonSliderVal,
  setPromptAspectRatio,
  setPromptQuality,
  setPromptStyle,
  setPromptText
} from '../stores/generation.store'
import { setActiveTab } from '../stores/ui.store'

export const GenerateTab: React.FC = () => {
  const promptText = useStore($promptText)
  const promptStyle = useStore($promptStyle)
  const promptAspectRatio = useStore($promptAspectRatio)
  const promptQuality = useStore($promptQuality)
  const promptModel = useStore($promptModel)
  const generatedImages = useStore($generatedImages)
  const isGenerating = useStore($isGenerating)
  const comparisonImage = useStore($comparisonImage)
  const comparisonSliderVal = useStore($comparisonSliderVal)

  const { createLayer } = useLayers()

  const handleGenerate = () => {
    generationService.generate({
      prompt: promptText,
      style: promptStyle,
      aspectRatio: promptAspectRatio,
      quality: promptQuality,
      model: promptModel,
      numImages: 4
    })
  }

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden">
      {/* Left controls sidebar */}
      <div className="w-80 shrink-0 border-r border-white/8 bg-[#0D0E15] p-4 flex flex-col gap-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">Generate Visuals</h3>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-white/60">Describe your image:</label>
          <textarea
            className="min-h-[96px] w-full resize-none rounded-xl border border-white/8 bg-black/40 p-3 text-xs leading-relaxed placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-[#8b46ff]"
            onChange={e => setPromptText(e.target.value)}
            placeholder="Describe your design. E.g., 'Model in an Ankara dress, golden hour sunset...'"
            value={promptText}
          />
        </div>

        {/* Style selector */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-white/60">Style Preset:</label>
          <select
            className="rounded-xl border border-white/8 bg-black/40 p-2.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-[#8b46ff]"
            onChange={e => setPromptStyle(e.target.value)}
            value={promptStyle}
          >
            {STYLE_PRESETS.map(s => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        {/* Aspect Ratio selector */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-white/60">Aspect Ratio:</label>
          <div className="grid grid-cols-4 gap-1">
            {(Object.keys(ASPECT_RATIOS) as AspectRatioType[]).map(ratio => (
              <button
                className={cn(
                  'rounded-lg border px-2 py-1.5 text-[0.625rem] font-bold uppercase transition',
                  promptAspectRatio === ratio
                    ? 'border-[#8b46ff] bg-[#8b46ff]/10 text-white'
                    : 'border-white/8 bg-black/25 text-white/55 hover:text-white'
                )}
                key={ratio}
                onClick={() => setPromptAspectRatio(ratio)}
              >
                {ratio}
              </button>
            ))}
          </div>
        </div>

        {/* Quality selector */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-white/60">Quality:</label>
          <select
            className="rounded-xl border border-white/8 bg-black/40 p-2.5 text-xs text-white focus:outline-none"
            onChange={e => setPromptQuality(e.target.value as QualityType)}
            value={promptQuality}
          >
            {(Object.keys(QUALITY_PRESETS) as QualityType[]).map(q => (
              <option key={q} value={q}>
                {QUALITY_PRESETS[q].label}
              </option>
            ))}
          </select>
        </div>

        <Button
          className="mt-auto h-10 w-full rounded-xl font-bold bg-[#8b46ff] hover:bg-[#783bdc] text-white"
          disabled={isGenerating}
          onClick={handleGenerate}
        >
          {isGenerating ? 'Generating...' : 'Generate Variations'}
        </Button>
      </div>

      {/* Variations Output Viewport */}
      <div className="flex-1 p-6 flex flex-col gap-4 overflow-y-auto">
        <h4 className="text-sm font-bold">Generated Variations</h4>
        {generatedImages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center border border-dashed border-white/8 rounded-2xl bg-[#0D0E15]/30">
            <IconSparkles className="size-12 text-white/20 mb-3" />
            <p className="text-xs text-white/40">Your generated images will appear here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {generatedImages.map((img, i) => (
              <div className="group relative overflow-hidden rounded-xl border border-white/8 bg-black/40 shadow-lg" key={i}>
                <img alt={`Variation ${i + 1}`} className="w-full object-cover" src={img} />
                <div className="absolute inset-0 bg-black/70 flex items-center justify-center gap-3 opacity-0 transition group-hover:opacity-100">
                  <Button
                    className="h-8 text-[0.6875rem]"
                    onClick={() => {
                      const layer = createEmptyLayer(`Generation ${i + 1}`, 'image')
                      layer.imageUrl = img
                      layer.dataUrl = img
                      createLayer(layer.name, 'image')
                      setActiveTab('canvas')
                    }}
                  >
                    Edit on Canvas
                  </Button>
                  <Button
                    className="h-8 text-[0.6875rem]"
                    onClick={() => setComparisonImage(img)}
                    variant="secondary"
                  >
                    Compare
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Comparison Overlay Panel */}
        {comparisonImage && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-8">
            <div className="relative w-full max-w-4xl bg-[#0D0E15] border border-white/8 rounded-2xl p-6 flex flex-col gap-4">
              <div className="flex justify-between items-center">
                <span className="text-sm font-bold">Compare Generations</span>
                <Button className="h-8" onClick={() => setComparisonImage(null)} variant="secondary">
                  Close
                </Button>
              </div>

              <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-white/8">
                <img alt="Original" className="absolute inset-0 size-full object-cover" src={generatedImages[0]} />

                <div
                  className="absolute inset-y-0 right-0 overflow-hidden"
                  style={{ width: `${100 - comparisonSliderVal}%` }}
                >
                  <img
                    alt="Modified"
                    className="absolute right-0 top-0 h-full max-w-none object-cover"
                    src={comparisonImage}
                    style={{ width: '800px', height: '100%' }}
                  />
                </div>

                <input
                  className="absolute inset-x-0 bottom-4 accent-[#8b46ff] z-10"
                  max="100"
                  min="0"
                  onChange={e => setComparisonSliderVal(parseInt(e.target.value))}
                  type="range"
                  value={comparisonSliderVal}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
