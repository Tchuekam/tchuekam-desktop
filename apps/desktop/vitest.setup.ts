// Vitest global setup.
//
// Node >= 22 ships an experimental built-in `localStorage` (gated behind
// `--localstorage-file`). Under the test runner it can shadow jsdom's Web
// Storage with a partial object that is missing `clear()`/`key()`, which
// breaks every test that resets state via `window.localStorage.clear()`.
//
// We install a complete in-memory implementation, but only when the runtime's
// storage is incomplete — so a healthy jsdom localStorage is left untouched.

class MemoryStorage implements Storage {
  private store = new Map<string, string>()
  get length(): number {
    return this.store.size
  }
  clear(): void {
    this.store.clear()
  }
  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }
  removeItem(key: string): void {
    this.store.delete(key)
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value))
  }
}

function ensureStorage(name: 'localStorage' | 'sessionStorage'): void {
  const existing = (globalThis as Record<string, unknown>)[name] as Storage | undefined
  const complete =
    !!existing &&
    typeof existing.clear === 'function' &&
    typeof existing.setItem === 'function' &&
    typeof existing.getItem === 'function' &&
    typeof existing.key === 'function'
  if (complete) return

  const impl = new MemoryStorage()
  Object.defineProperty(globalThis, name, { value: impl, configurable: true, writable: true })
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, name, { value: impl, configurable: true, writable: true })
  }
}

ensureStorage('localStorage')
ensureStorage('sessionStorage')
