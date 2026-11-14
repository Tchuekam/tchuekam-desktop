/**
 * Unified provider layer for Image Studio.
 *
 * - FAL.ai (primary) runs *through the TchueKAM backend* (`/api/images/*`): the
 *   backend holds the key, runs the persisted job, and registers the asset in
 *   shared history. This layer therefore never re-registers FAL results.
 * - MuAPI (optional) is called from the studio client with the MuAPI key; its
 *   results are registered in shared history here, exactly once.
 *
 * Routing is capability-based. If the resolved provider cannot perform the
 * requested operation the call is REJECTED before submission — it is never
 * silently sent to another provider (different cost, quality, privacy).
 */

import {
  generateStudioImages,
  getStudioAssetData,
  processImageEdit,
  saveToStudioLibrary,
  type ImageGenStudioResponse
} from '@/hermes'

import { getActiveStudioProvider, getProviderKey, type StudioProviderId } from './credentialService'
import {
  generateAudio as muapiGenerateAudio,
  generateI2I as muapiGenerateI2I,
  generateImage as muapiGenerateImage,
  generateVideo as muapiGenerateVideo
  // @ts-expect-error JS module without type declarations
} from './open-generative-ai/packages/studio/src/muapi.js'

export type Capability = 'text-to-image' | 'image-to-image' | 'image-edit' | 'text-to-video' | 'audio'

/** What each provider can actually do through this integration today. */
export const PROVIDER_CAPABILITIES: Record<StudioProviderId, readonly Capability[]> = {
  fal: ['text-to-image', 'image-edit'],
  muapi: ['text-to-image', 'image-to-image', 'text-to-video', 'audio']
}

export interface GenerationParams {
  prompt: string
  model?: string
  provider?: StudioProviderId
  aspect_ratio?: string
  quality?: string
  style?: string
  resolution?: string
  duration?: number
  image_url?: string
  images_list?: string[]
  seed?: number
  options?: Record<string, unknown>
  workspaceId?: string
  conversationId?: string
  /** Stable per user action; resubmitting it can never generate twice. */
  clientRequestId?: string
  onRequestId?: (requestId: string) => void
}

export interface GenerationResult {
  id: string
  url: string
  prompt: string
  provider: StudioProviderId
  model: string
  type: 'image' | 'video' | 'audio'
  createdAt: number
  jobId?: string
}

export class ProviderError extends Error {
  status: number
  errorType: string
  provider: StudioProviderId
  userMessage: string

  constructor(message: string, status = 500, errorType = 'provider_error', provider: StudioProviderId = 'fal') {
    super(message)
    this.name = 'ProviderError'
    this.status = status
    this.errorType = errorType
    this.provider = provider
    this.userMessage = message
  }
}

const FAL_MODEL_PREFIXES = ['fal-ai/', 'bytedance/', 'alibaba/']

export function isFalModelId(model?: string): boolean {
  return !!model && FAL_MODEL_PREFIXES.some(p => model.startsWith(p))
}

/**
 * Resolve provider: explicit choice > model id > user's active provider, then
 * verify the capability. Throws `unsupported_operation` instead of falling back.
 */
export function resolveProvider(params: GenerationParams, capability: Capability): StudioProviderId {
  const provider: StudioProviderId =
    params.provider ?? (isFalModelId(params.model) ? 'fal' : params.model ? 'muapi' : getActiveStudioProvider())

  if (!PROVIDER_CAPABILITIES[provider].includes(capability)) {
    const name = provider === 'fal' ? 'FAL.ai' : 'MuAPI'
    throw new ProviderError(
      `${name} does not support ${capability.replace(/-/g, ' ')} in TchueKAM Studio. Pick a model from a provider that does.`,
      400,
      'unsupported_operation',
      provider
    )
  }

  return provider
}

const newRequestId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `req-${Date.now()}-${Math.random()}`

function raiseAuth(provider: StudioProviderId, message: string): never {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('tchuekam:auth-required', { detail: { provider, message } }))
  }

  throw new ProviderError(message, 401, 'auth_invalid_credentials', provider)
}

async function requireKey(provider: StudioProviderId): Promise<string> {
  const key = await getProviderKey(provider)

  if (!key) {
    throw new ProviderError(
      `${provider === 'fal' ? 'FAL.ai' : 'MuAPI'} is not configured. Add its API key in Settings.`,
      401,
      'auth_missing_credentials',
      provider
    )
  }

  return key
}

/** Run a FAL generation through the backend job and return its real asset. */
async function runBackendImageJob(params: GenerationParams, modelId: string): Promise<GenerationResult> {
  const resp: ImageGenStudioResponse = await generateStudioImages({
    prompt: params.prompt,
    style: params.style || 'photorealistic',
    aspectRatio: params.aspect_ratio || '16:9',
    quality: params.quality || 'medium',
    model: modelId,
    numImages: 1,
    provider: 'fal',
    workspaceId: params.workspaceId,
    conversationId: params.conversationId,
    clientRequestId: params.clientRequestId || newRequestId()
  })

  if (!resp?.success || !resp.asset) {
    const type = resp?.error_type || 'generation_failed'
    const message = resp?.error || 'FAL.ai image generation failed.'

    if (type === 'auth_invalid_credentials') {
      raiseAuth('fal', message)
    }

    throw new ProviderError(message, type === 'auth_missing_credentials' ? 401 : 502, type, 'fal')
  }

  let url = resp.asset.url || resp.images?.[0] || ''

  if (!url) {
    // Stored only as a backend file: fetch real bytes, never a placeholder.
    const data = await getStudioAssetData(resp.asset.id)

    if (!data?.success || !data.dataUrl) {
      throw new ProviderError('The image was generated but could not be loaded.', 502, 'asset_unavailable', 'fal')
    }

    url = data.dataUrl
  }

  return {
    id: resp.asset.id,
    url,
    prompt: params.prompt,
    provider: 'fal',
    model: resp.asset.model || modelId,
    type: 'image',
    createdAt: resp.asset.createdAt ?? Date.now(),
    jobId: resp.jobId
  }
}

/** Register a MuAPI result once (FAL results are registered by the backend). */
async function registerMuapiAsset(
  r: { id: string; url: string },
  p: GenerationParams,
  model: string,
  type: 'image' | 'video' | 'audio'
): Promise<void> {
  try {
    await saveToStudioLibrary({
      id: r.id,
      url: r.url,
      name: p.prompt.slice(0, 40),
      prompt: p.prompt,
      provider: 'muapi',
      model,
      studioType: type,
      mimeType: type === 'video' ? 'video/mp4' : type === 'audio' ? 'audio/mpeg' : undefined,
      parameters: { aspect_ratio: p.aspect_ratio, quality: p.quality, resolution: p.resolution },
      workspaceId: p.workspaceId,
      conversationId: p.conversationId,
      tags: ['muapi', model, type],
      favorite: false
    })
  } catch (err) {
    // The asset exists at the provider; history registration failing must be
    // visible in logs but must not discard a paid-for result.
    console.warn('[studio] could not register asset in shared history:', err)
  }
}

function normalizeMuapi(err: unknown, provider: StudioProviderId = 'muapi'): never {
  if (err instanceof ProviderError) {
    throw err
  }

  const msg = err instanceof Error ? err.message : String(err)

  if (/\b(401|403)\b|not authorized|unauthor/i.test(msg)) {
    raiseAuth(provider, 'MuAPI rejected the API key. Check it in Settings.')
  }

  if (/\b429\b|quota|rate limit|insufficient/i.test(msg)) {
    throw new ProviderError('MuAPI rate limit or balance reached.', 429, 'quota_or_rate_limited', provider)
  }

  throw new ProviderError(msg || 'MuAPI request failed.', 502, 'generation_failed', provider)
}

const requirePrompt = (params: GenerationParams, provider: StudioProviderId) => {
  if (!params.prompt?.trim()) {
    throw new ProviderError('A prompt is required.', 400, 'validation_error', provider)
  }
}

/** Text-to-image. */
export async function generateUnifiedImage(params: GenerationParams): Promise<GenerationResult> {
  const provider = resolveProvider(params, 'text-to-image')
  requirePrompt(params, provider)

  if (provider === 'fal') {
    return runBackendImageJob(params, params.model || 'fal-ai/flux-2/klein/9b')
  }

  const apiKey = await requireKey('muapi')
  const model = params.model || 'flux-schnell'

  try {
    const res = await muapiGenerateImage(apiKey, {
      model,
      prompt: params.prompt.trim(),
      aspect_ratio: params.aspect_ratio || '1:1',
      quality: params.quality,
      seed: params.seed,
      onRequestId: params.onRequestId
    })

    if (!res?.url) {
      throw new ProviderError('MuAPI finished without returning an image.', 502, 'empty_result', 'muapi')
    }

    const id = res.id || newRequestId()
    await registerMuapiAsset({ id, url: res.url }, params, model, 'image')

    return { id, url: res.url, prompt: params.prompt, provider: 'muapi', model, type: 'image', createdAt: Date.now() }
  } catch (err) {
    return normalizeMuapi(err)
  }
}

/** Image-to-image. FAL has no input-image path in this integration → rejected up front. */
export async function generateUnifiedI2I(params: GenerationParams): Promise<GenerationResult> {
  const provider = resolveProvider(params, 'image-to-image')

  if (!params.image_url && !params.images_list?.length) {
    throw new ProviderError('A reference image is required.', 400, 'validation_error', provider)
  }

  const apiKey = await requireKey('muapi')
  const model = params.model || 'flux-kontext-dev-i2i'

  try {
    const res = await muapiGenerateI2I(apiKey, {
      model,
      prompt: params.prompt?.trim(),
      image_url: params.image_url ?? params.images_list?.[0],
      images_list: params.images_list,
      aspect_ratio: params.aspect_ratio || '1:1',
      quality: params.quality,
      seed: params.seed
    })

    if (!res?.url) {
      throw new ProviderError('MuAPI finished without returning an image.', 502, 'empty_result', 'muapi')
    }

    const id = res.id || newRequestId()
    await registerMuapiAsset({ id, url: res.url }, params, model, 'image')

    return { id, url: res.url, prompt: params.prompt, provider: 'muapi', model, type: 'image', createdAt: Date.now() }
  } catch (err) {
    return normalizeMuapi(err)
  }
}

/** Upscale via the backend (registers its own asset). */
export async function editUnifiedImage(
  params: GenerationParams & { operation: string; image: string }
): Promise<GenerationResult> {
  const provider = resolveProvider({ ...params, provider: params.provider ?? 'fal' }, 'image-edit')
  const resp = await processImageEdit({
    image: params.image,
    operation: params.operation || 'upscale',
    prompt: params.prompt,
    options: params.options
  })

  if (!resp?.success || !resp.image) {
    throw new ProviderError(resp?.error || 'Image edit failed.', 502, 'edit_failed', provider)
  }

  return {
    id: newRequestId(),
    url: resp.image,
    prompt: params.prompt || `Edit: ${params.operation}`,
    provider,
    model: 'clarity-upscaler',
    type: 'image',
    createdAt: Date.now()
  }
}

/** Text-to-video: MuAPI only (FAL video is not wired to a backend endpoint). */
export async function generateUnifiedVideo(params: GenerationParams): Promise<GenerationResult> {
  const provider = resolveProvider(params, 'text-to-video')
  requirePrompt(params, provider)
  const apiKey = await requireKey('muapi')
  const model = params.model || 'kling-video'

  try {
    const res = await muapiGenerateVideo(apiKey, {
      model,
      prompt: params.prompt.trim(),
      aspect_ratio: params.aspect_ratio,
      duration: params.duration,
      resolution: params.resolution
    })

    if (!res?.url) {
      throw new ProviderError('MuAPI finished without returning a video.', 502, 'empty_result', 'muapi')
    }

    const id = res.id || newRequestId()
    await registerMuapiAsset({ id, url: res.url }, params, model, 'video')

    return { id, url: res.url, prompt: params.prompt, provider: 'muapi', model, type: 'video', createdAt: Date.now() }
  } catch (err) {
    return normalizeMuapi(err)
  }
}

/** Audio: MuAPI only. */
export async function generateUnifiedAudio(params: GenerationParams): Promise<GenerationResult> {
  const provider = resolveProvider({ ...params, provider: params.provider ?? 'muapi' }, 'audio')
  requirePrompt(params, provider)
  const apiKey = await requireKey('muapi')
  const model = params.model || 'suno-v3'

  try {
    const res = await muapiGenerateAudio(apiKey, { model, prompt: params.prompt.trim(), ...params.options })

    if (!res?.url) {
      throw new ProviderError('MuAPI finished without returning audio.', 502, 'empty_result', 'muapi')
    }

    const id = res.id || newRequestId()
    await registerMuapiAsset({ id, url: res.url }, params, model, 'audio')

    return { id, url: res.url, prompt: params.prompt, provider: 'muapi', model, type: 'audio', createdAt: Date.now() }
  } catch (err) {
    return normalizeMuapi(err)
  }
}
