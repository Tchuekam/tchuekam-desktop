/**
 * TchueKAM Image Studio v2 — OpenAI Provider Adapter
 */

import { analyzeStudioImage, generateStudioImages, performStudioOCR, processImageEdit } from '../../../../hermes'
import type {
  EditParams,
  EditResult,
  GenerationParams,
  GenerationResult,
  OCRParams,
  OCRResult,
  VisionParams,
  VisionResult
} from '../../core/types'
import type { IStudioProvider, ProviderCapabilities } from '../base/IStudioProvider'

export class OpenAIProvider implements IStudioProvider {
  readonly id = 'openai'
  readonly name = 'OpenAI DALL-E & GPT-4o'
  readonly description = 'High quality text-to-image and GPT-4o multimodal vision'

  readonly capabilities: ProviderCapabilities = {
    textToImage: true,
    imageToImage: true,
    inpainting: true,
    outpainting: true,
    removeBackground: true,
    replaceBackground: true,
    visionAnalysis: true,
    ocr: true,
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
      model: params.model || 'gpt-image-2-medium',
      numImages: params.numImages
    })

    return {
      success: res.success,
      images: res.images,
      provider: this.id,
      error: res.error
    }
  }

  async inpaint(params: EditParams): Promise<EditResult> {
    const res = await processImageEdit({
      image: params.image,
      mask: params.mask,
      operation: params.operation,
      prompt: params.prompt,
      options: params.options
    })

    return {
      success: res.success,
      image: res.image,
      provider: this.id,
      error: res.error
    }
  }

  async removeBackground(params: EditParams): Promise<EditResult> {
    return this.inpaint(params)
  }

  async replaceBackground(params: EditParams): Promise<EditResult> {
    return this.inpaint(params)
  }

  async analyzeVision(params: VisionParams): Promise<VisionResult> {
    const res = await analyzeStudioImage({
      image: params.image,
      mode: params.mode,
      question: params.question
    })

    return {
      success: res.success,
      result: res.result,
      colors: res.colors,
      provider: this.id,
      error: res.error
    }
  }

  async performOCR(params: OCRParams): Promise<OCRResult> {
    const res = await performStudioOCR({
      image: params.image
    })

    return {
      success: res.success,
      text: res.text,
      provider: this.id,
      error: res.error
    }
  }
}
