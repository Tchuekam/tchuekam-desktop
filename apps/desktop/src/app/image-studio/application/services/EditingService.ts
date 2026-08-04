/**
 * TchueKAM Image Studio v2 — AI Photo Editing Service
 */

import type { EditParams, EditResult } from '../../core/types'
import { providerRegistry } from '../../providers/registry'
import { getActiveLayer, updateLayer } from '../../stores/layer.store'
import { showToast } from '../../stores/ui.store'

export class EditingService {
  public async processEdit(params: EditParams): Promise<EditResult> {
    const activeLayer = getActiveLayer()
    if (!activeLayer) {
      showToast('Please select a layer to edit', 'error')
      return { success: false, error: 'No active layer selected' }
    }

    try {
      const provider = providerRegistry.getProvider()
      if (!provider.inpaint) {
        showToast('Active provider does not support AI editing', 'error')
        return { success: false, error: 'Unsupported capability' }
      }

      const res = await provider.inpaint(params)

      if (res.success && res.image) {
        updateLayer(activeLayer.id, l => ({
          ...l,
          imageUrl: res.image
        }))
        showToast(`Successfully applied: ${params.operation}`)
        return res
      } else {
        showToast(res.error || 'Failed to apply AI edit', 'error')
        return res
      }
    } catch (err: any) {
      const msg = err.message || 'Edit processing error'
      showToast(msg, 'error')
      return { success: false, error: msg }
    }
  }
}

export const editingService = new EditingService()
