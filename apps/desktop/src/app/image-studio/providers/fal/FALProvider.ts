/**
 * TchueKAM Image Studio v2 — FAL AI Provider Adapter
 */

import { generateStudioImages } from '../../../../hermes'
import type { GenerationParams, GenerationResult } from '../../core/types'
import type { IStudioProvider, ProviderCapabilities } from '../base/IStudioProvider'

export class FALProvider implements IStudioProvider {
  readonly id = 'fal'
  readonly name = 'FAL AI (FLUX 2 Klein 9B)'
  readonly description = 'Ultra-fast generation via FLUX 2 Klein models'

  readonly capabilities: ProviderCapabilities = {
    textToImage: true,
    imageToImage: true,
    inpainting: true,
    outpainting: false,
    removeBackground: false,
    replaceBackground: false,
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
      model: 'fal-ai/flux-2/klein/9b',
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
