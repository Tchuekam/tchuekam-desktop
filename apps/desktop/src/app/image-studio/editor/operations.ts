/**
 * TchueKAM Image Studio v2 — Outpaint, Remove, Replace, Upscale, Background Modules
 */

import type { EditParams, EditResult } from '../core/types'
import { editingService } from '../application/services/EditingService'

export async function processOutpaint(image: string, prompt: string): Promise<EditResult> {
  const params: EditParams = { image, operation: 'outpaint', prompt }
  return editingService.processEdit(params)
}

export async function processRemoveBackground(image: string): Promise<EditResult> {
  const params: EditParams = { image, operation: 'remove-bg' }
  return editingService.processEdit(params)
}

export async function processReplaceBackground(image: string, prompt: string): Promise<EditResult> {
  const params: EditParams = { image, operation: 'replace-bg', prompt }
  return editingService.processEdit(params)
}

export async function processUpscale(image: string): Promise<EditResult> {
  const params: EditParams = { image, operation: 'upscale' }
  return editingService.processEdit(params)
}
