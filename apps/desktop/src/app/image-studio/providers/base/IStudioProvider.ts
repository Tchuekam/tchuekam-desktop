/**
 * TchueKAM Image Studio v2 — Provider Interface & Capability Contract
 */

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

export interface ProviderCapabilities {
  textToImage: boolean
  imageToImage: boolean
  inpainting: boolean
  outpainting: boolean
  removeBackground: boolean
  replaceBackground: boolean
  visionAnalysis: boolean
  ocr: boolean
  upscaling: boolean
}

export interface IStudioProvider {
  readonly id: string
  readonly name: string
  readonly description: string
  readonly capabilities: ProviderCapabilities

  isAvailable(): Promise<boolean> | boolean

  textToImage?(params: GenerationParams): Promise<GenerationResult>
  imageToImage?(params: GenerationParams & { sourceImage: string }): Promise<GenerationResult>
  inpaint?(params: EditParams): Promise<EditResult>
  outpaint?(params: EditParams): Promise<EditResult>
  removeBackground?(params: EditParams): Promise<EditResult>
  replaceBackground?(params: EditParams): Promise<EditResult>
  analyzeVision?(params: VisionParams): Promise<VisionResult>
  performOCR?(params: OCRParams): Promise<OCRResult>
  upscale?(params: EditParams): Promise<EditResult>
}
