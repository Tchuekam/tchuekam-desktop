/**
 * TchueKAM Image Studio v2 — UnderstandTab Component
 */

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { VISION_ANALYSIS_MODES } from '../core/constants'
import type { AnalysisModeType } from '../core/types'
import { visionService } from '../application/services/VisionService'
import { setBrushColor } from '../stores/canvas.store'
import { showToast } from '../stores/ui.store'

export const UnderstandTab: React.FC = () => {
  const [analysisImage, setAnalysisImage] = useState<string | null>(null)
  const [analysisMode, setAnalysisMode] = useState<AnalysisModeType>('describe')
  const [analysisQuestion, setAnalysisQuestion] = useState('')
  const [analysisResult, setAnalysisResult] = useState<string>('')
  const [analysisColors, setAnalysisColors] = useState<string[]>([])
  const [isAnalyzing, setIsAnalyzing] = useState(false)

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = event => {
      setAnalysisImage(event.target?.result as string)
    }
    reader.readAsDataURL(file)
  }

  const handleAnalyze = async () => {
    if (!analysisImage) return
    setIsAnalyzing(true)

    const res = await visionService.analyze({
      image: analysisImage,
      mode: analysisMode,
      question: analysisQuestion
    })

    if (res.success) {
      setAnalysisResult(res.result || '')
      if (res.colors) setAnalysisColors(res.colors)
    }
    setIsAnalyzing(false)
  }

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
      <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">Image Understanding</h3>

        <div className="flex flex-col gap-3">
          <label className="text-xs font-semibold text-white/60">Upload Image:</label>
          <div className="relative border border-dashed border-white/12 rounded-xl p-4 flex flex-col items-center justify-center bg-black/20 hover:bg-black/30 cursor-pointer">
            <input accept="image/*" className="absolute inset-0 opacity-0 cursor-pointer" onChange={handleUpload} type="file" />
            <span className="text-[0.6875rem] text-white/40">Drag & drop or Click to upload</span>
          </div>
          {analysisImage && (
            <img alt="Preview" className="h-32 object-contain rounded-lg border border-white/8" src={analysisImage} />
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-white/60">Analysis Mode:</label>
          <select
            className="rounded-xl border border-white/8 bg-black/40 p-2.5 text-xs text-white focus:outline-none"
            onChange={e => setAnalysisMode(e.target.value as AnalysisModeType)}
            value={analysisMode}
          >
            {VISION_ANALYSIS_MODES.map(m => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        {analysisMode === 'qa' && (
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-white/60">Ask your question:</label>
            <Input
              className="h-9 rounded-xl border border-white/8 bg-black/40 text-xs"
              onChange={e => setAnalysisQuestion(e.target.value)}
              placeholder="E.g., What is written on the billboard?"
              value={analysisQuestion}
            />
          </div>
        )}

        <Button
          className="w-full h-10 rounded-xl bg-[#8b46ff] hover:bg-[#783bdc] text-white font-bold"
          disabled={isAnalyzing}
          onClick={handleAnalyze}
        >
          {isAnalyzing ? 'Analyzing...' : 'Analyze Image'}
        </Button>
      </div>

      <div className="flex-1 flex flex-col gap-4">
        <h4 className="text-sm font-bold">Analysis Results</h4>
        <div className="flex-1 border border-white/8 rounded-2xl bg-black/40 p-6 overflow-y-auto leading-relaxed text-sm text-white/80">
          {analysisResult ? (
            <div className="flex flex-col gap-4">
              <p>{analysisResult}</p>

              {analysisColors.length > 0 && (
                <div className="flex flex-col gap-2 mt-4">
                  <span className="text-xs font-bold text-white/40 uppercase">Color Palette</span>
                  <div className="flex gap-2">
                    {analysisColors.map(c => (
                      <button
                        className="size-8 rounded-lg border border-white/8 shadow-sm transition hover:scale-105 active:scale-95"
                        key={c}
                        onClick={() => {
                          setBrushColor(c)
                          showToast(`Set brush color to ${c}`)
                        }}
                        style={{ backgroundColor: c }}
                        title={`Set brush to ${c}`}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="size-full flex flex-col items-center justify-center text-white/30 text-xs">
              No active analysis results. Upload an image to start.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
