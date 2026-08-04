/**
 * TchueKAM Image Studio v2 — Domain Models & Factories
 */

import { DEFAULT_CANVAS_HEIGHT, DEFAULT_CANVAS_WIDTH } from '../constants'
import type {
  CanvasLayerState,
  LibraryAssetItem,
  PromptVariable,
  SavedPromptItem,
  StudioProjectData,
  StudioProjectMetadata,
  StudioProjectSettings
} from '../types'

export function createEmptyLayer(
  name: string = 'Layer',
  type: CanvasLayerState['type'] = 'paint',
  width: number = DEFAULT_CANVAS_WIDTH,
  height: number = DEFAULT_CANVAS_HEIGHT
): CanvasLayerState {
  return {
    id: `layer-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
    name,
    visible: true,
    opacity: 1.0,
    type,
    x: 0,
    y: 0,
    width,
    height
  }
}

export function createBaseBackgroundLayer(
  width: number = DEFAULT_CANVAS_WIDTH,
  height: number = DEFAULT_CANVAS_HEIGHT
): CanvasLayerState {
  return {
    id: 'base-layer',
    name: 'Background Layer',
    visible: true,
    opacity: 1.0,
    type: 'paint',
    x: 0,
    y: 0,
    width,
    height
  }
}

export function createDefaultMetadata(name: string = 'Untitled Project'): StudioProjectMetadata {
  const now = Date.now()

  return {
    id: `project-${now}-${Math.random().toString(36).substr(2, 5)}`,
    name,
    createdAt: now,
    updatedAt: now,
    version: '2.0.0',
    width: DEFAULT_CANVAS_WIDTH,
    height: DEFAULT_CANVAS_HEIGHT
  }
}

export function createDefaultSettings(): StudioProjectSettings {
  return {
    showGrid: false,
    snapGuides: true,
    autoSave: true,
    activeProviderId: 'openai'
  }
}

export function createDefaultProject(name: string = 'New Project'): StudioProjectData {
  const baseLayer = createBaseBackgroundLayer()

  return {
    metadata: createDefaultMetadata(name),
    settings: createDefaultSettings(),
    layers: [baseLayer],
    activeLayerId: baseLayer.id,
    prompts: [],
    promptVariables: [
      { name: 'subject', value: 'Ankara model' },
      { name: 'lighting', value: 'golden hour sunset' },
      { name: 'setting', value: 'Douala streets' }
    ],
    generationHistory: [],
    editHistory: [],
    assets: []
  }
}

export function serializeProject(project: StudioProjectData): string {
  return JSON.stringify({
    ...project,
    metadata: {
      ...project.metadata,
      updatedAt: Date.now()
    }
  }, null, 2)
}

export function deserializeProject(jsonStr: string): StudioProjectData {
  const parsed = JSON.parse(jsonStr)

  if (!parsed.metadata || !parsed.layers) {
    throw new Error('Invalid project format')
  }

  return parsed as StudioProjectData
}
