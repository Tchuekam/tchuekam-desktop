/**
 * Tests for electron/auto-updater.cjs.
 *
 * Run with: node --test electron/auto-updater.test.cjs
 * (Wired into npm test:desktop:platforms in package.json.)
 *
 * The guarantee under test: auto-update is OPTIONAL and must never crash the
 * app. Whatever the state of electron-updater (present, missing, broken),
 * initAutoUpdater() returns without throwing and reports a sane status.
 */

const test = require('node:test')
const assert = require('node:assert/strict')
const Module = require('node:module')
const path = require('node:path')

const AU_PATH = require.resolve('./auto-updater.cjs')

// Load a fresh copy of auto-updater.cjs with injected fakes for the 'electron'
// and 'electron-updater' module specifiers. The mocks stay active until the
// returned restore() is called, because electron-updater is required lazily
// (inside initAutoUpdater) rather than at module load. Real timers are stubbed
// so the active path doesn't leave the test process alive for 30s / 4h.
function loadWith({ isPackaged = true, updater = 'ok' } = {}) {
  const events = {}
  const fakeUpdater = {
    autoDownload: undefined,
    autoInstallOnAppQuit: undefined,
    allowPrerelease: undefined,
    on(evt, cb) { events[evt] = cb },
    checkForUpdates() { return Promise.resolve() },
    quitAndInstall() {}
  }
  const fakeElectron = {
    app: { isPackaged, getVersion: () => '9.9.9', on() {} },
    dialog: { showMessageBox: async () => ({ response: 1 }) },
    BrowserWindow: { getAllWindows: () => [] }
  }

  const origLoad = Module._load
  const origSetTimeout = global.setTimeout
  const origSetInterval = global.setInterval
  global.setTimeout = () => 0
  global.setInterval = () => 0

  Module._load = function (request, parent, isMain) {
    if (request === 'electron') return fakeElectron
    if (request === 'electron-updater') {
      if (updater === 'throw') throw new Error("Cannot find module 'electron-updater'")
      return { autoUpdater: fakeUpdater }
    }
    return origLoad.apply(this, arguments)
  }

  delete require.cache[AU_PATH]
  const mod = require(AU_PATH)

  const restore = () => {
    Module._load = origLoad
    global.setTimeout = origSetTimeout
    global.setInterval = origSetInterval
    delete require.cache[AU_PATH]
  }
  return { mod, fakeUpdater, events, restore }
}

test('exposes the expected API and starts in "pending" status', () => {
  const { mod, restore } = loadWith()
  try {
    assert.deepEqual(
      Object.keys(mod).sort(),
      ['checkNow', 'getUpdaterStatus', 'initAutoUpdater', 'shutdownAutoUpdater']
    )
    assert.equal(mod.getUpdaterStatus(), 'pending')
  } finally { restore() }
})

test('pre-init checkNow / shutdown are safe no-ops', () => {
  const { mod, restore } = loadWith()
  try {
    assert.doesNotThrow(() => mod.checkNow())
    assert.doesNotThrow(() => mod.shutdownAutoUpdater())
  } finally { restore() }
})

test('dev mode (not packaged): disabled, never touches electron-updater', () => {
  const { mod, restore } = loadWith({ isPackaged: false })
  try {
    assert.doesNotThrow(() => mod.initAutoUpdater())
    assert.equal(mod.getUpdaterStatus(), 'dev')
  } finally { restore() }
})

test('packaged + updater available: becomes active and wires listeners', () => {
  const { mod, fakeUpdater, restore } = loadWith({ isPackaged: true, updater: 'ok' })
  try {
    assert.doesNotThrow(() => mod.initAutoUpdater())
    assert.equal(mod.getUpdaterStatus(), 'active')
    // setupListeners ran -> these were configured on the updater instance.
    assert.equal(fakeUpdater.autoDownload, true)
    assert.equal(fakeUpdater.autoInstallOnAppQuit, true)
    assert.equal(fakeUpdater.allowPrerelease, false)
    mod.shutdownAutoUpdater()
  } finally { restore() }
})

test('packaged + electron-updater missing: disabled, app still launches', () => {
  const { mod, restore } = loadWith({ isPackaged: true, updater: 'throw' })
  try {
    // The crux of the bug fix: a missing module must NOT throw out of init.
    assert.doesNotThrow(() => mod.initAutoUpdater())
    assert.equal(mod.getUpdaterStatus(), 'unavailable')
    // And subsequent checks stay safe.
    assert.doesNotThrow(() => mod.checkNow())
  } finally { restore() }
})

test('init is idempotent', () => {
  const { mod, restore } = loadWith({ isPackaged: false })
  try {
    mod.initAutoUpdater()
    const first = mod.getUpdaterStatus()
    mod.initAutoUpdater()
    assert.equal(mod.getUpdaterStatus(), first)
  } finally { restore() }
})
