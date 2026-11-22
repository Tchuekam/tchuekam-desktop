function loadAutoUpdater() {
  try {
    return require('electron-updater').autoUpdater
  } catch {
    // Workspace dev mode resolves root node_modules; packaged builds stage runtime deps in resources/native-deps.
  }

  if (typeof process.resourcesPath === 'string' && process.resourcesPath) {
    const nodePath = require('node:path')
    const stagedPath = nodePath.join(
      process.resourcesPath,
      'native-deps',
      'node_modules',
      'electron-updater'
    )
    try {
      return require(stagedPath).autoUpdater
    } catch (err) {
      console.warn('[auto-updater] Failed to load staged electron-updater:', err)
    }
  }

  return null
}

const autoUpdater = loadAutoUpdater()

const { app, dialog, BrowserWindow } = require('electron')

const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000 // 4 hours
const INITIAL_DELAY_MS = 30 * 1000           // 30 seconds after launch

let initialized = false
let intervalHandle = null

function broadcast(channel, payload) {
  for (const win of BrowserWindow.getAllWindows()) {
    try { win.webContents.send(channel, payload) } catch {}
  }
}

function setupListeners() {
  if (!autoUpdater) return
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
      setImmediate(() => autoUpdater.quitAndInstall(false, true))
    }
  })

  autoUpdater.on('error', (err) => {
    broadcast('tchuekam:update:error', { message: String(err && err.message || err) })
  })
}

function checkNow() {
  if (!app.isPackaged || !autoUpdater) return
  try {
    autoUpdater.checkForUpdates().catch(() => {})
  } catch {}
}

function initAutoUpdater() {
  if (initialized || !autoUpdater || !app.isPackaged) return
  initialized = true


  setupListeners()

  // First check after a short delay so the UI is up and the user isn't
  // greeted by a network call competing with startup work.
  setTimeout(checkNow, INITIAL_DELAY_MS)

  // Then re-check every 4 hours so long-running sessions get updates too.
  intervalHandle = setInterval(checkNow, CHECK_INTERVAL_MS)
}

function shutdownAutoUpdater() {
  if (intervalHandle) {
    clearInterval(intervalHandle)
    intervalHandle = null
  }
}

module.exports = { initAutoUpdater, shutdownAutoUpdater, checkNow }
