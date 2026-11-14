import { JSDOM } from 'jsdom'

export const testDom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/'
})

const win = testDom.window as unknown as Record<string, unknown>

for (const key of [
  'window',
  'document',
  'navigator',
  'Node',
  'Element',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLSelectElement',
  'HTMLTextAreaElement',
  'HTMLButtonElement',
  'HTMLFormElement',
  'HTMLAnchorElement',
  'Event',
  'CustomEvent',
  'MouseEvent',
  'KeyboardEvent',
  'InputEvent',
  'FocusEvent',
  'FileReader',
  'File',
  'Blob',
  'localStorage',
  'MutationObserver',
  'getComputedStyle'
]) {
  if (key in win) {
    Object.defineProperty(globalThis, key, {
      configurable: true,
      value: win[key],
      writable: true
    })
  }
}

