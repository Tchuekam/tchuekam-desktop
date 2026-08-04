/**
 * TchueKAM Image Studio v2 — Provider Registry
 */

import {
  $activeCapabilities,
  $activeProviderId,
  $availableProviders,
  type ProviderMeta
} from '../stores/provider.store'

import type { IStudioProvider } from './base/IStudioProvider'
import { ComfyUIProvider } from './comfyui/ComfyUIProvider'
import { FALProvider } from './fal/FALProvider'
import { GeminiProvider } from './gemini/GeminiProvider'
import { LocalProvider } from './local/LocalProvider'
import { OpenAIProvider } from './openai/OpenAIProvider'
import { ReplicateProvider } from './replicate/ReplicateProvider'
import { StabilityProvider } from './stability/StabilityProvider'

class ProviderRegistry {
  private providers: Map<string, IStudioProvider> = new Map()

  constructor() {
    this.register(new OpenAIProvider())
    this.register(new FALProvider())
    this.register(new GeminiProvider())
    this.register(new ReplicateProvider())
    this.register(new ComfyUIProvider())
    this.register(new StabilityProvider())
    this.register(new LocalProvider())
  }

  public register(provider: IStudioProvider): void {
    this.providers.set(provider.id, provider)
    this.refreshAvailableProviders()
  }

  public getProvider(id?: string): IStudioProvider {
    const targetId = id || $activeProviderId.get()
    const provider = this.providers.get(targetId) || this.providers.get('local')!
    return provider
  }

  public setActiveProvider(id: string): boolean {
    const provider = this.providers.get(id)
    if (!provider) return false

    $activeProviderId.set(id)
    $activeCapabilities.set(provider.capabilities)
    return true
  }

  public async refreshAvailableProviders(): Promise<ProviderMeta[]> {
    const list: ProviderMeta[] = []

    for (const [id, provider] of this.providers.entries()) {
      let isAvail = false
      try {
        isAvail = await provider.isAvailable()
      } catch {
        isAvail = false
      }

      list.push({
        id,
        name: provider.name,
        description: provider.description,
        isAvailable: isAvail,
        capabilities: provider.capabilities
      })
    }

    $availableProviders.set(list)

    const activeId = $activeProviderId.get()
    const current = this.providers.get(activeId)
    if (current) {
      $activeCapabilities.set(current.capabilities)
    }

    return list
  }
}

export const providerRegistry = new ProviderRegistry()
