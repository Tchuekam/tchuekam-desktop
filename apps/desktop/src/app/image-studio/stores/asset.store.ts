/**
 * TchueKAM Image Studio v2 — Asset Library Store
 */

import { atom } from 'nanostores'
import type { LibraryAssetItem, SavedPromptItem } from '../core/types'

export const $libraryItems = atom<LibraryAssetItem[]>([])
export const $libraryFilter = atom<'all' | 'favorites' | 'images' | 'designs'>('all')
export const $librarySearch = atom<string>('')
export const $selectedLibraryItem = atom<LibraryAssetItem | null>(null)

export const $savedPrompts = atom<SavedPromptItem[]>([])

export function setLibraryItems(items: LibraryAssetItem[]) {
  $libraryItems.set(items)
}

export function setLibraryFilter(filter: 'all' | 'favorites' | 'images' | 'designs') {
  $libraryFilter.set(filter)
}

export function setLibrarySearch(search: string) {
  $librarySearch.set(search)
}

export function setSelectedLibraryItem(item: LibraryAssetItem | null) {
  $selectedLibraryItem.set(item)
}

export function setSavedPrompts(prompts: SavedPromptItem[]) {
  $savedPrompts.set(prompts)
}
