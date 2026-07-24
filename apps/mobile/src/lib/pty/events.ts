import { ConnectionStatus, LatencyStats, PtyFrame } from "./types";

type EventListener = (...args: any[]) => void;

export class PtyEventEmitter {
  private listeners: Map<string, Set<EventListener>> = new Map();

  public on(event: string, fn: EventListener): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(fn);

    return () => this.off(event, fn);
  }

  public off(event: string, fn: EventListener): void {
    const set = this.listeners.get(event);
    if (set) {
      set.delete(fn);
    }
  }

  public emit(event: string, ...args: any[]): void {
    const set = this.listeners.get(event);
    if (set) {
      set.forEach((fn) => {
        try {
          fn(...args);
        } catch (err) {
          console.warn("Event listener error on " + event + ":", err);
        }
      });
    }
  }

  public removeAllListeners(): void {
    this.listeners.clear();
  }
}
