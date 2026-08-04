/**
 * TchueKAM Image Studio v2 — Asset Storage Adapter
 */

import { deleteFromStudioLibrary, getStudioLibrary, saveToStudioLibrary } from '../../../hermes'
import type { LibraryAssetItem } from '../core/types'
import { setLibraryItems } from '../stores/asset.store'

export class AssetStorage {
  public async loadAll(): Promise<LibraryAssetItem[]> {
    const res = await getStudioLibrary()
    if (res.success) {
      setLibraryItems(res.items)
      return res.items
    }
    return []
  }

  public async saveItem(item: Omit<LibraryAssetItem, 'createdAt'>): Promise<boolean> {
    const res = await saveToStudioLibrary(item)
    if (res.success) {
      await this.loadAll()
      return true
    }
    return false
  }

  public async deleteItem(id: string): Promise<boolean> {
    const res = await deleteFromStudioLibrary(id)
    if (res.success) {
      await this.loadAll()
      return true
    }
    return false
  }
}

export const assetStorage = new AssetStorage()
