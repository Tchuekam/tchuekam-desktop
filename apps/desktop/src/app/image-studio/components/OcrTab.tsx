/**
 * TchueKAM Image Studio v2 — OcrTab Component
 */

import { IconCopy } from '@tabler/icons-react'
import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { OcrExportFormat } from '../core/types'
import { ocrService } from '../application/services/VisionService'
import { exporter } from '../export/exporter'
import { showToast } from '../stores/ui.store'

export const OcrTab: React.FC = () => {
  const [ocrImage, setOcrImage] = useState<string | null>(null)
  const [ocrResult, setOcrResult] = useState('')
  const [isOcring, setIsOcring] = useState(false)
  const [ocrExportFormat, setOcrExportFormat] = useState<OcrExportFormat>('markdown')

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = event => {
      setOcrImage(event.target?.result as string)
    }
    reader.readAsDataURL(file)
  }

  const handleOcr = async () => {
    if (!ocrImage) return
    setIsOcring(true)
    const res = await ocrService.performOCR({ image: ocrImage })
    if (res.success) {
      setOcrResult(res.text || '')
    }
    setIsOcring(false)
  }

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
      <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">OCR Text Pull</h3>

        <div className="flex flex-col gap-3">
          <label className="text-xs font-semibold text-white/60">Upload Source:</label>
          <div className="relative border border-dashed border-white/12 rounded-xl p-4 flex flex-col items-center justify-center bg-black/20 hover:bg-black/30 cursor-pointer">
            <input accept="image/*" className="absolute inset-0 opacity-0 cursor-pointer" onChange={handleUpload} type="file" />
            <span className="text-[0.6875rem] text-white/40">Select receipts, business cards, documents</span>
          </div>
          {ocrImage && (
            <img alt="Preview" className="h-32 object-contain rounded-lg border border-white/8" src={ocrImage} />
          )}
        </div>

        <Button
          className="w-full h-10 rounded-xl bg-[#8b46ff] hover:bg-[#783bdc] text-white font-bold"
          disabled={isOcring}
          onClick={handleOcr}
        >
          {isOcring ? 'Extracting Text...' : 'Perform OCR'}
        </Button>

        {ocrResult && (
          <div className="flex flex-col gap-2 mt-auto">
            <label className="text-xs font-semibold text-white/60">Export format:</label>
            <div className="grid grid-cols-3 gap-1">
              {(['markdown', 'txt', 'json'] as OcrExportFormat[]).map(fmt => (
                <button
                  className={cn(
                    'rounded-lg border py-1 text-[0.625rem] font-bold uppercase transition',
                    ocrExportFormat === fmt
                      ? 'border-[#8b46ff] bg-[#8b46ff]/10 text-white'
                      : 'border-white/8 bg-black/25 text-white/50'
                  )}
                  key={fmt}
                  onClick={() => setOcrExportFormat(fmt)}
                >
                  {fmt}
                </button>
              ))}
            </div>
            <Button
              className="w-full h-9 rounded-xl mt-1.5"
              onClick={() => exporter.exportOCRText(ocrResult, ocrExportFormat)}
              variant="secondary"
            >
              Export File
            </Button>
          </div>
        )}
      </div>

      <div className="flex-1 flex flex-col gap-4">
        <div className="flex justify-between items-center">
          <h4 className="text-sm font-bold">Extracted Text Content</h4>
          {ocrResult && (
            <Button
              className="h-8"
              onClick={() => {
                navigator.clipboard.writeText(ocrResult)
                showToast('Copied to clipboard')
              }}
              variant="outline"
            >
              <IconCopy className="mr-1.5" size="0.9rem" /> Copy
            </Button>
          )}
        </div>
        <div className="flex-1 border border-white/8 rounded-2xl bg-black/40 p-6 overflow-y-auto leading-relaxed text-sm text-white/80 font-mono">
          {ocrResult ? (
            <pre className="whitespace-pre-wrap">{ocrResult}</pre>
          ) : (
            <div className="size-full flex flex-col items-center justify-center text-white/30 text-xs">
              Extracted text details will render here.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
