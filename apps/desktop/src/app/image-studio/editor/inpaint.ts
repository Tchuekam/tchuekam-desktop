/**
 * TchueKAM Image Studio v2 — Inpaint Module
 */

import type { EditParams, EditResult } from '../core/types'
import { editingService } from '../application/services/EditingService'

export async function processInpaint(image: string, mask: string, prompt: string): Promise<EditResult> {
  const params: EditParams = {
    image,
    mask,
    operation: 'inpaint',
    prompt
  }
  return editingService.processEdit(params)
}
