/**
 * TchueKAM Image Studio v2 — Vision & OCR Services
 */

import type { OCRParams, OCRResult, VisionParams, VisionResult } from '../../core/types'
import { providerRegistry } from '../../providers/registry'
import { showToast } from '../../stores/ui.store'

export class VisionService {
  public async analyze(params: VisionParams): Promise<VisionResult> {
    if (!params.image) {
      showToast('Please upload an image first', 'error')
      return { success: false, error: 'No image provided' }
    }

    try {
      const provider = providerRegistry.getProvider()
      if (!provider.analyzeVision) {
        showToast('Active provider does not support vision analysis', 'error')
        return { success: false, error: 'Capability not supported' }
      }

      const res = await provider.analyzeVision(params)
      if (res.success) {
        showToast('Image analyzed successfully!')
      } else {
        showToast(res.error || 'Analysis failed', 'error')
      }
      return res
    } catch (err: any) {
      const msg = err.message || 'Vision analysis error'
      showToast(msg, 'error')
      return { success: false, error: msg }
    }
  }
}

export class OcrService {
  public async performOCR(params: OCRParams): Promise<OCRResult> {
    if (!params.image) {
      showToast('Please upload an image first', 'error')
      return { success: false, error: 'No image provided' }
    }

    try {
      const provider = providerRegistry.getProvider()
      if (!provider.performOCR) {
        showToast('Active provider does not support OCR', 'error')
        return { success: false, error: 'Capability not supported' }
      }

      const res = await provider.performOCR(params)
      if (res.success) {
        showToast('Text extracted successfully!')
      } else {
        showToast(res.error || 'OCR failed', 'error')
      }
      return res
    } catch (err: any) {
      const msg = err.message || 'OCR error'
      showToast(msg, 'error')
      return { success: false, error: msg }
    }
  }
}

export const visionService = new VisionService()
export const ocrService = new OcrService()
