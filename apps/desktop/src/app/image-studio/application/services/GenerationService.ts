/**
 * TchueKAM Image Studio v2 — Generation Service
 */

import type { GenerationParams, GenerationResult } from '../../core/types'
import { providerRegistry } from '../../providers/registry'
import { $generatedImages, $isGenerating, setGeneratedImages, setIsGenerating } from '../../stores/generation.store'
import { showToast } from '../../stores/ui.store'
import { eventBus } from '../events/EventBus'

export class GenerationService {
  public async generate(params: GenerationParams): Promise<GenerationResult> {
    if (!params.prompt.trim()) {
      showToast('Please type a prompt first', 'error')
      return { success: false, error: 'Empty prompt' }
    }

    setIsGenerating(true)

    // Variable interpolation
    let finalPrompt = params.prompt
    if (params.variables) {
      Object.entries(params.variables).forEach(([k, v]) => {
        finalPrompt = finalPrompt.replace(new RegExp(`{${k}}`, 'g'), v)
      })
    }

    try {
      const provider = providerRegistry.getProvider(params.model)
      const res = await provider.textToImage!({
        ...params,
        prompt: finalPrompt
      })

      if (res.success && res.images) {
        setGeneratedImages(res.images)
        eventBus.emit('GenerationCompleted', { imagesCount: res.images.length, provider: res.provider })
        showToast('Images generated successfully!')
        return res
      } else {
        showToast(res.error || 'Generation failed', 'error')
        eventBus.emit('GenerationFailed', { error: res.error })
        return res
      }
    } catch (err: any) {
      const msg = err.message || 'Generation error'
      showToast(msg, 'error')
      eventBus.emit('GenerationFailed', { error: msg })
      return { success: false, error: msg }
    } finally {
      setIsGenerating(false)
    }
  }
}

export const generationService = new GenerationService()
