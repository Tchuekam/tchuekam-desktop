// TchueKAM auto-updater — checks GitHub Releases for new versions and
// installs them on quit. Publishes update lifecycle events to the renderer
// for in-app UI, and to PostHog for analytics.
//
// IMPORTANT: auto-update is an OPTIONAL convenience. It must NEVER prevent the
// application from launching. electron-updater is a main-process runtime
// dependency, and because packaged builds ship no node_modules in the asar
// (see scripts/before-build.cjs + scripts/stage-native-deps.cjs), it is staged
// into resources/native-deps/ and require()'d back from there at runtime. If
// that module is missing or fails to load for ANY reason, every function in
// this file degrades to a safe no-op and the app starts normally.

const { app, dialog, BrowserWindow } = require('electron')
const path = require('node:path')

const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000 // 4 hours
const INITIAL_DELAY_MS = 30 * 1000           // 30 seconds after launch

let initialized = false
let intervalHandle = null
let autoUpdater = null      // resolved lazily; null means "unavailable"
let updaterStatus = 'pending' // 'pending' | 'active' | 'unavailable' | 'dev'

function log(...args) {
  console.log('[auto-updater]', ...args)
}

function warn(...args) {
  console.warn('[auto-updater]', ...args)
}

// Lazily resolve electron-updater. In dev / hoisted layouts the normal require
// succeeds. In packaged builds node_modules is not in the asar, so we fall
// back to the copy staged under resources/native-deps/node_modules/ (mirrors
// the node-pty fallback in main.cjs). Returns the autoUpdater instance, or
// null if it cannot be loaded — callers must treat null as "disabled".
function loadAutoUpdater() {
  if (autoUpdater) return autoUpdater
  try {
    ;({ autoUpdater } = require('electron-updater'))
    return autoUpdater
  } catch (errPrimary) {
    try {
      const resourcesPath = process.resourcesPath
      if (resourcesPath) {
        const staged = path.join(resourcesPath, 'native-deps', 'node_modules', 'electron-updater')
        ;({ autoUpdater } = require(staged))
        return autoUpdater
      }
    } catch (errFallback) {
      warn('electron-updater unavailable from staged resources:', String(errFallback && errFallback.message || errFallback))
    }
    warn('electron-updater could not be loaded; auto-update disabled for this session:', String(errPrimary && errPrimary.message || errPrimary))
    autoUpdater = null
    return null
  }
}

function broadcast(channel, payload) {
  for (const win of BrowserWindow.getAllWindows()) {
    try { win.webContents.send(channel, payload) } catch {}
  }
}

function setupListeners() {
  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.allowPrerelease = false

  autoUpdater.on('checking-for-update', () => {
    broadcast('tchuekam:update:checking', { ts: Date.now() })
  })

  autoUpdater.on('update-available', (info) => {
    broadcast('tchuekam:update:available', {
      version: info.version,
      releaseDate: info.releaseDate,
      releaseNotes: info.releaseNotes
    })
  })

  autoUpdater.on('update-not-available', (info) => {
    broadcast('tchuekam:update:none', { version: info.version })
  })

  autoUpdater.on('download-progress', (progress) => {
    broadcast('tchuekam:update:progress', {
      percent: Math.round(progress.percent),
      bytesPerSecond: progress.bytesPerSecond,
      transferred: progress.transferred,
      total: progress.total
    })
  })

  autoUpdater.on('update-downloaded', async (info) => {
    broadcast('tchuekam:update:ready', {
      version: info.version,
      releaseDate: info.releaseDate
    })

    try {
      const choice = await dialog.showMessageBox({
        type: 'info',
        buttons: ['Restart now', 'Later'],
        defaultId: 0,
        cancelId: 1,
        title: 'TchueKAM update ready',
        message: `TchueKAM ${info.version} is ready to install.`,
        detail: 'The update will be applied the next time you launch TchueKAM. Restart now to apply it immediately.'
      })

      if (choice.response === 0) {
        setImmediate(() => {
          try { autoUpdater.quitAndInstall(false, true) } catch (err) { warn('quitAndInstall failed:', String(err && err.message || err)) }
        })
      }
    } catch (err) {
      warn('update-downloaded handler failed:', String(err && err.message || err))
    }
  })

  autoUpdater.on('error', (err) => {
    broadcast('tchuekam:update:error', { message: String(err && err.message || err) })
  })
}

function checkNow() {
  // Skip updates in dev mode (no packaged app to update) or when the updater
  // failed to load.
  if (!autoUpdater) return
  if (!app.isPackaged) return
  try {
    autoUpdater.checkForUpdates().catch((err) => {
      warn('checkForUpdates rejected:', String(err && err.message || err))
    })
  } catch (err) {
    warn('checkForUpdates threw:', String(err && err.message || err))
  }
}

// Initialize the auto-updater. Wrapped end-to-end so a failure here can never
// crash startup — the worst case is that auto-update is silently disabled and
// the app launches normally.
function initAutoUpdater() {
  if (initialized) return
  initialized = true

  try {
    if (!app.isPackaged) {
      updaterStatus = 'dev'
      log('dev mode: auto-update disabled')
      return // dev mode: no-op
    }

    if (!loadAutoUpdater()) {
      updaterStatus = 'unavailable'
      return // module missing/broken: stay disabled, app continues
    }

    setupListeners()
    updaterStatus = 'active'
    log('initialized; first check in', INITIAL_DELAY_MS / 1000, 's')

    // First check after a short delay so the UI is up and the user isn't
    // greeted by a network call competing with startup work.
    setTimeout(checkNow, INITIAL_DELAY_MS)

    // Then re-check every 4 hours so long-running sessions get updates too.
    intervalHandle = setInterval(checkNow, CHECK_INTERVAL_MS)
  } catch (err) {
    updaterStatus = 'unavailable'
    warn('initialization failed; auto-update disabled:', String(err && err.message || err))
  }
}

function shutdownAutoUpdater() {
  if (intervalHandle) {
    clearInterval(intervalHandle)
    intervalHandle = null
  }
}

// Returns a short status string for startup diagnostics / logging.
function getUpdaterStatus() {
  return updaterStatus
}

module.exports = { initAutoUpdater, shutdownAutoUpdater, checkNow, getUpdaterStatus }
