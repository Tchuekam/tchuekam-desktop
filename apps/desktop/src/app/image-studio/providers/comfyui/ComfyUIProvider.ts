/**
 * TchueKAM Image Studio v2 — ComfyUI Provider Adapter
 */

import { generateStudioImages } from '../../../../hermes'
import type { GenerationParams, GenerationResult } from '../../core/types'
import type { IStudioProvider, ProviderCapabilities } from '../base/IStudioProvider'

export class ComfyUIProvider implements IStudioProvider {
  readonly id = 'comfyui'
  readonly name = 'ComfyUI Local/Remote Workflow'
  readonly description = 'Custom node-based workflow execution backend'

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
      model: 'comfyui-local-workflow',
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
