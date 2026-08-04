/**
 * TchueKAM Image Studio v2 — Domain Event Bus
 */

export type StudioEventType =
  | 'LayerCreated'
  | 'LayerDeleted'
  | 'LayerReordered'
  | 'CanvasUpdated'
  | 'GenerationCompleted'
  | 'GenerationFailed'
  | 'HistoryChanged'
  | 'ProjectLoaded'
  | 'ProjectSaved'
  | 'ProviderChanged'

export interface StudioEvent<T = any> {
  type: StudioEventType
  timestamp: number
  payload: T
}

type EventListener<T = any> = (event: StudioEvent<T>) => void

class EventBus {
  private listeners: Map<StudioEventType, Set<EventListener>> = new Map()

  public subscribe<T = any>(type: StudioEventType, listener: EventListener<T>): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }

    const listenerSet = this.listeners.get(type)!
    listenerSet.add(listener)

    return () => {
      listenerSet.delete(listener)
    }
  }

  public emit<T = any>(type: StudioEventType, payload: T): void {
    const event: StudioEvent<T> = {
      type,
      timestamp: Date.now(),
      payload
    }

    const listenerSet = this.listeners.get(type)
    if (listenerSet) {
      listenerSet.forEach(listener => {
        try {
          listener(event)
        } catch (err) {
          console.error(`[EventBus] Error handling event ${type}:`, err)
        }
      })
    }
  }
}

export const eventBus = new EventBus()
