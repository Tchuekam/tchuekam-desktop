/**
 * TchueKAM Image Studio v2 — System Constants & Presets
 */

import type {
  AnalysisModeType,
  AspectRatioType,
  BrushConfig,
  EditOperationType,
  QualityType
} from '../types'

export const DEFAULT_CANVAS_WIDTH = 800
export const DEFAULT_CANVAS_HEIGHT = 600

export const DEFAULT_BRUSH_CONFIG: BrushConfig = {
  color: '#8b46ff',
  size: 15,
  hardness: 0.8,
  opacity: 1.0
}

export const STYLE_PRESETS = [
  { id: 'photorealistic', label: 'Photorealistic' },
  { id: 'anime', label: 'Anime / Manga' },
  { id: 'cinematic', label: 'Cinematic 3D' },
  { id: 'watercolor', label: 'Watercolor' },
  { id: 'sketch', label: 'Sketch / Ink' },
  { id: 'pixel art', label: 'Pixel Art' },
  { id: '3d render', label: '3D Render' },
  { id: 'oil painting', label: 'Oil Painting' },
  { id: 'logo', label: 'Vector Logo' },
  { id: 'icon', label: 'App Icon' },
  { id: 'flat illustration', label: 'Flat Illustration' },
  { id: 'concept art', label: 'Concept Art' }
] as const

export const ASPECT_RATIOS: Record<AspectRatioType, { label: string; ratio: number; width: number; height: number }> = {
  square: { label: '1:1 Square', ratio: 1.0, width: 800, height: 800 },
  landscape: { label: '16:9 Landscape', ratio: 16 / 9, width: 960, height: 540 },
  portrait: { label: '9:16 Portrait', ratio: 9 / 16, width: 540, height: 960 },
  cinematic: { label: '21:9 Cinematic', ratio: 21 / 9, width: 1050, height: 450 }
}

export const QUALITY_PRESETS: Record<QualityType, { label: string; description: string }> = {
  low: { label: 'Draft Quality', description: 'Fastest generation, lower detail' },
  medium: { label: 'Standard Quality', description: 'Balanced speed and fidelity' },
  high: { label: 'Production Quality', description: 'Maximum detail, slower render' }
}

export const EDIT_OPERATIONS: Array<{ id: EditOperationType; label: string; desc: string }> = [
  { id: 'inpaint', label: 'AI Inpainting', desc: 'Edit parts of image inside active mask' },
  { id: 'outpaint', label: 'AI Outpainting', desc: 'Expand boundaries of the image' },
  { id: 'remove-bg', label: 'Remove Background', desc: 'Isolate main subject' },
  { id: 'replace-bg', label: 'Replace Background', desc: 'Swap scene backgrounds' },
  { id: 'magic-erase', label: 'AI Magic Erase', desc: 'Remove unwanted objects/people' },
  { id: 'upscale', label: 'AI Upscale 4x', desc: 'Enhance details & resolution' },
  { id: 'sharpen', label: 'AI Sharpen', desc: 'Fix blurred outlines' }
]

export const VISION_ANALYSIS_MODES: Array<{ id: AnalysisModeType; label: string }> = [
  { id: 'describe', label: 'General Description' },
  { id: 'qa', label: 'Ask Questions (Q&A)' },
  { id: 'diagram', label: 'Explain Diagram' },
  { id: 'ui', label: 'Identify UI Elements' },
  { id: 'objects', label: 'Detect Objects' },
  { id: 'color', label: 'Extract Color Palette' },
  { id: 'scene', label: 'Scene Understanding' }
]

export const MOCKUP_TYPES = [
  { id: 'phone', label: 'Smartphone' },
  { id: 'laptop', label: 'Laptop Frame' },
  { id: 't-shirt', label: 'T-Shirt Overlay' },
  { id: 'hoodie', label: 'Hoodie Overlay' },
  { id: 'mug', label: 'Coffee Mug' },
  { id: 'billboard', label: 'Street Billboard' },
  { id: 'box', label: 'Packaging Box' },
  { id: 'bag', label: 'Shopping Bag' }
] as const

export const DESIGN_TEMPLATES = [
  'Logo Design',
  'Poster / Flyer',
  'Social Media Post',
  'Business Card',
  'YouTube Thumbnail',
  'Website Banner',
  'App Icon',
  'Book Cover',
  'Packaging Label'
] as const
