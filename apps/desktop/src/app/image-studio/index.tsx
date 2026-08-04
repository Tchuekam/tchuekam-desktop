/**
 * TchueKAM Image Studio v2 Module Entry Point
 */

export { ImageStudioView } from './components/ImageStudioLayout'
export type { StudioProjectData, CanvasLayerState, LibraryAssetItem, SavedPromptItem } from './core/types'
export { projectService } from './application/services/ProjectService'
export { providerRegistry } from './providers/registry'
export { commandBus } from './application/commands/CommandBus'
export { eventBus } from './application/events/EventBus'
