/**
 * TchueKAM Image Studio v2 — LibraryTab Component
 */

import { IconFolder, IconHeart, IconSparkles, IconSquare } from '@tabler/icons-react'
import { useStore } from '@nanostores/react'
import React, { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { getStudioLibrary, saveToStudioLibrary } from '../../../hermes'
import { createEmptyLayer } from '../core/models'
import type { LibraryAssetItem } from '../core/types'
import { useLayers } from '../hooks/useLayers'

import {
  $libraryFilter,
  $libraryItems,
  $librarySearch,
  setLibraryFilter,
  setLibraryItems,
  setLibrarySearch
} from '../stores/asset.store'
import { showToast } from '../stores/ui.store'

export const LibraryTab: React.FC = () => {
  const libraryItems = useStore($libraryItems)
  const libraryFilter = useStore($libraryFilter)
  const librarySearch = useStore($librarySearch)
  const { createLayer, layers } = useLayers()

  const loadLibrary = async () => {
    try {
      const res = await getStudioLibrary()
      if (res.success) {
        setLibraryItems(res.items)
      }
    } catch {
      showToast('Failed to load asset library', 'error')
    }
  }

  useEffect(() => {
    loadLibrary()
  }, [])

  const handleItemClick = (item: LibraryAssetItem) => {
    const layer = createEmptyLayer(item.name, 'image')
    layer.imageUrl = item.url
    layer.dataUrl = item.url
    createLayer(layer.name, 'image')
    showToast(`Loaded ${item.name} onto active canvas`)
  }

  const handleSaveCanvasToLibrary = async () => {
    const activeData = layers[0]?.dataUrl || ''
    if (!activeData) return

    try {
      await saveToStudioLibrary({
        id: `lib-${Date.now()}`,
        name: `Canvas Export ${libraryItems.length + 1}`,
        url: activeData,
        tags: ['canvas', 'export'],
        favorite: false
      })
      loadLibrary()
      showToast('Saved current canvas to library')
    } catch {
      showToast('Error saving to library', 'error')
    }
  }

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
      <div className="w-60 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
        <span className="text-xs font-bold uppercase tracking-wider text-white/50">Asset Collections</span>

        <div className="flex flex-col gap-1">
          {[
            { id: 'all', label: 'All Assets', icon: IconFolder },
            { id: 'favorites', label: 'Favorites', icon: IconHeart },
            { id: 'images', label: 'Images', icon: IconSparkles },
            { id: 'designs', label: 'Designs', icon: IconSquare }
          ].map(coll => (
            <button
              className={cn(
                'flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs font-bold transition',
                libraryFilter === coll.id ? 'bg-[#8b46ff]/16 text-[#8b46ff]' : 'text-white/60 hover:bg-white/3 hover:text-white'
              )}
              key={coll.id}
              onClick={() => setLibraryFilter(coll.id as any)}
            >
              <coll.icon size="0.95rem" />
              {coll.label}
            </button>
          ))}
        </div>

        <div className="mt-auto border-t border-white/8 pt-3 flex flex-col gap-2">
          <Button className="w-full text-xs h-9 rounded-xl" onClick={handleSaveCanvasToLibrary}>
            Add Canvas To Library
          </Button>
        </div>
      </div>

      <div className="flex-1 flex flex-col gap-4">
        <div className="flex justify-between items-center">
          <h4 className="text-sm font-bold">Library Workspace</h4>
          <Input
            className="w-48 h-8 rounded-lg text-xs"
            onChange={e => setLibrarySearch(e.target.value)}
            placeholder="Search assets..."
            value={librarySearch}
          />
        </div>

        <ScrollArea className="flex-1 border border-white/8 rounded-2xl bg-black/40 p-4">
          {libraryItems.length === 0 ? (
            <div className="size-full flex flex-col items-center justify-center text-white/30 text-xs">
              Asset library is currently empty.
            </div>
          ) : (
            <div className="grid grid-cols-4 gap-4">
              {libraryItems
                .filter(item => (libraryFilter === 'favorites' ? item.favorite : true))
                .filter(item => item.name.toLowerCase().includes(librarySearch.toLowerCase()))
                .map(item => (
                  <div
                    className="group relative aspect-square rounded-xl border border-white/8 bg-black/20 overflow-hidden cursor-pointer shadow hover:border-[#8b46ff]"
                    key={item.id}
                    onClick={() => handleItemClick(item)}
                  >
                    <img alt={item.name} className="size-full object-cover" src={item.url} />
                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-end p-2 transition">
                      <span className="text-[0.625rem] font-bold text-white truncate w-full">{item.name}</span>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  )
}
