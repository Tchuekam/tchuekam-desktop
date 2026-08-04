/**
 * TchueKAM Image Studio v2 — Generation Store
 */

import { atom } from 'nanostores'
import type { AspectRatioType, QualityType } from '../core/types'

export const $promptText = atom<string>('')
export const $promptStyle = atom<string>('photorealistic')
export const $promptAspectRatio = atom<AspectRatioType>('square')
export const $promptQuality = atom<QualityType>('medium')
export const $promptModel = atom<string>('gpt-image-2-medium')

export const $generatedImages = atom<string[]>([])
export const $isGenerating = atom<boolean>(false)

export const $comparisonImage = atom<string | null>(null)
export const $comparisonSliderVal = atom<number>(50)

export function setPromptText(text: string) {
  $promptText.set(text)
}

export function setPromptStyle(style: string) {
  $promptStyle.set(style)
}

export function setPromptAspectRatio(aspectRatio: AspectRatioType) {
  $promptAspectRatio.set(aspectRatio)
}

export function setPromptQuality(quality: QualityType) {
  $promptQuality.set(quality)
}

export function setPromptModel(model: string) {
  $promptModel.set(model)
}

export function setGeneratedImages(images: string[]) {
  $generatedImages.set(images)
}

export function setIsGenerating(generating: boolean) {
  $isGenerating.set(generating)
}

export function setComparisonImage(img: string | null) {
  $comparisonImage.set(img)
}

export function setComparisonSliderVal(val: number) {
  $comparisonSliderVal.set(val)
}
