/**
 * TchueKAM Image Studio v2 — Provider Store
 */

import { atom } from 'nanostores'
import type { ProviderCapabilities } from '../providers/base/IStudioProvider'

export interface ProviderMeta {
  id: string
  name: string
  description: string
  isAvailable: boolean
  capabilities: ProviderCapabilities
}

export const $activeProviderId = atom<string>('local')
export const $availableProviders = atom<ProviderMeta[]>([])
export const $activeCapabilities = atom<ProviderCapabilities>({
  textToImage: true,
  imageToImage: false,
  inpainting: false,
  outpainting: false,
  removeBackground: false,
  replaceBackground: false,
  visionAnalysis: false,
  ocr: false,
  upscaling: false
})

export function setActiveProviderId(id: string) {
  $activeProviderId.set(id)
}

export function setAvailableProviders(providers: ProviderMeta[]) {
  $availableProviders.set(providers)
}

export function setActiveCapabilities(capabilities: ProviderCapabilities) {
  $activeCapabilities.set(capabilities)
}
