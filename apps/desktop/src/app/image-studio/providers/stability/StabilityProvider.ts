/**
 * TchueKAM Image Studio v2 — Stability AI Provider Adapter
 */

import { generateStudioImages } from '../../../../hermes'
import type { GenerationParams, GenerationResult } from '../../core/types'
import type { IStudioProvider, ProviderCapabilities } from '../base/IStudioProvider'

export class StabilityProvider implements IStudioProvider {
  readonly id = 'stability'
  readonly name = 'Stability AI (SD3 / Ultra)'
  readonly description = 'Stable Diffusion 3 & Ultra generation models'

  readonly capabilities: ProviderCapabilities = {
    textToImage: true,
    imageToImage: true,
    inpainting: true,
    outpainting: true,
    removeBackground: true,
    replaceBackground: true,
    visionAnalysis: false,
    ocr: false,
    upscaling: true
  }

  async isAvailable(): Promise<boolean> {
    return true
  }

  async textToImage(params: GenerationParams): Promise<GenerationResult> {
    const res = await generateStudioImages({
      prompt: params.prompt,
      style: params.style,
      aspectRatio: params.aspectRatio,
      quality: params.quality,
      model: 'sd3-ultra',
      numImages: params.numImages
    })

    return {
      success: res.success,
      images: res.images,
      provider: this.id,
      error: res.error
    }
  }
}
