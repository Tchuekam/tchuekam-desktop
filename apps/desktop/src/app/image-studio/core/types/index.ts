/**
 * TchueKAM Image Studio v2 — Core Types
 */

export type StudioTab =
  | 'canvas'
  | 'generate'
  | 'edit'
  | 'understand'
  | 'ocr'
  | 'design'
  | 'mockups'
  | 'library'
  | 'prompts'

export type CanvasToolType = 'select' | 'brush' | 'eraser' | 'mask' | 'pan'

export type LayerType = 'paint' | 'image' | 'text' | 'mask'

export type AspectRatioType = 'square' | 'landscape' | 'portrait' | 'cinematic'

export type QualityType = 'low' | 'medium' | 'high'

export type AnalysisModeType =
  | 'describe'
  | 'qa'
  | 'diagram'
  | 'ui'
  | 'objects'
  | 'color'
  | 'scene'

export type EditOperationType =
  | 'inpaint'
  | 'outpaint'
  | 'remove-bg'
  | 'replace-bg'
  | 'magic-erase'
  | 'upscale'
  | 'sharpen'

export type OcrExportFormat = 'markdown' | 'txt' | 'word' | 'json' | 'csv'

export interface Point {
  x: number
  y: number
}

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export interface BrushConfig {
  color: string
  size: number
  hardness: number
  opacity: number
}

export interface CanvasLayerState {
  id: string
  name: string
  visible: boolean
  opacity: number // 0.0 to 1.0
  type: LayerType
  imageUrl?: string
  text?: string
  fontColor?: string
  fontSize?: number
  x: number
  y: number
  width: number
  height: number
  dataUrl?: string
}

export interface PromptVariable {
  name: string
  value: string
}

export interface SavedPromptItem {
  id: string
  prompt: string
  style: string
  favorite: boolean
  createdAt: number
}

export interface LibraryAssetItem {
  id: string
  name: string
  url: string
  tags: string[]
  favorite: boolean
  createdAt: number
}

export interface StudioProjectMetadata {
  id: string
  name: string
  createdAt: number
  updatedAt: number
  version: string
  width: number
  height: number
  thumbnailUrl?: string
}

export interface StudioProjectSettings {
  showGrid: boolean
  snapGuides: boolean
  autoSave: boolean
  activeProviderId: string
}

export interface StudioProjectData {
  metadata: StudioProjectMetadata
  settings: StudioProjectSettings
  layers: CanvasLayerState[]
  activeLayerId: string | null
  prompts: SavedPromptItem[]
  promptVariables: PromptVariable[]
  generationHistory: string[]
  editHistory: string[]
  assets: LibraryAssetItem[]
}

export interface GenerationParams {
  prompt: string
  style: string
  aspectRatio: AspectRatioType
  quality: QualityType
  model: string
  numImages: number
  variables?: Record<string, string>
}

export interface EditParams {
  image: string
  mask?: string
  operation: EditOperationType
  prompt?: string
  options?: Record<string, any>
}

export interface VisionParams {
  image: string
  mode: AnalysisModeType
  question?: string
}

export interface OCRParams {
  image: string
}

export interface GenerationResult {
  success: boolean
  images?: string[]
  provider?: string
  error?: string
}

export interface EditResult {
  success: boolean
  image?: string
  provider?: string
  error?: string
}

export interface VisionResult {
  success: boolean
  result?: string
  colors?: string[]
  provider?: string
  error?: string
}

export interface OCRResult {
  success: boolean
  text?: string
  provider?: string
  error?: string
}
