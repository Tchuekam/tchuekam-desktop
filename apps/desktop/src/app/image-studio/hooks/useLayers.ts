/**
 * TchueKAM Image Studio v2 — useLayers Hook
 */

import { useStore } from '@nanostores/react'
import { $activeLayerId, $layers } from '../stores/layer.store'
import { commandBus } from '../application/commands/CommandBus'
import {
  CreateLayerCommand,
  DeleteLayerCommand,
  DuplicateLayerCommand,
  ReorderLayersCommand,
  ToggleLayerVisibilityCommand,
  UpdateLayerOpacityCommand
} from '../application/commands/layerCommands'

export function useLayers() {
  const layers = useStore($layers)
  const activeLayerId = useStore($activeLayerId)
  const activeLayer = layers.find(l => l.id === activeLayerId) || null

  return {
    layers,
    activeLayerId,
    activeLayer,
    setActiveLayerId: (id: string | null) => $activeLayerId.set(id),
    createLayer: (name?: string, type?: any) => commandBus.dispatch(new CreateLayerCommand(name, type)),
    deleteLayer: (id: string) => commandBus.dispatch(new DeleteLayerCommand(id)),
    duplicateLayer: (id: string) => commandBus.dispatch(new DuplicateLayerCommand(id)),
    reorderLayers: (from: number, to: number) => commandBus.dispatch(new ReorderLayersCommand(from, to)),
    setLayerOpacity: (id: string, newOp: number, oldOp: number) =>
      commandBus.dispatch(new UpdateLayerOpacityCommand(id, newOp, oldOp)),
    toggleLayerVisibility: (id: string) => commandBus.dispatch(new ToggleLayerVisibilityCommand(id))
  }
}
