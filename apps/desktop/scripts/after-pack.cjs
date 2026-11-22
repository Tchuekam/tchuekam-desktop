/**
 * after-pack.cjs — electron-builder afterPack hook.
 *
 * Stamps the Hermes icon + identity onto the packed Windows Hermes.exe via
 * rcedit (delegated to set-exe-identity.cjs). This runs for EVERY packed build
 * — first install, `hermes desktop`, the installer's --update rebuild, and a
 * dev's manual `npm run pack` — so the branded exe can never silently revert
 * to the stock "Electron" icon/name (the bug when the stamp lived only in
 * install.ps1, which the update path doesn't use).
 *
 * Windows-only: rcedit edits PE resources, irrelevant on macOS/Linux where the
 * app identity comes from the bundle Info.plist / desktop entry. Best-effort:
 * a stamp failure must never fail an otherwise-good build (worst case is the
 * stock icon, not a broken app), so we log and resolve rather than throw.
 *
 * electron-builder passes a context with:
 *   - electronPlatformName: 'win32' | 'darwin' | 'linux'
 *   - appOutDir:            the unpacked app directory for this target
 *   - packager.appInfo.productFilename: the exe basename (e.g. 'Hermes')
 */

const fs = require('node:fs')
const path = require('node:path')

const { stampExeIdentity } = require('./set-exe-identity.cjs')

function resolvePackagedResourcesDir(context) {
  if (context.electronPlatformName === 'darwin') {
    const appName = context.packager?.appInfo?.productFilename || 'Tchuekam'
    return path.join(context.appOutDir, `${appName}.app`, 'Contents', 'Resources')
  }
  return path.join(context.appOutDir, 'resources')
}

function copyStagedRuntimeModules(desktopRoot, resourcesDir) {
  // electron-builder omits **/node_modules/** inside extraResources even when
  // staged under build/native-deps/. Copy the staged closure explicitly so
  // require(path.join(process.resourcesPath, 'native-deps', 'node_modules', ...))
  // resolves in packaged builds on all platforms.
  const src = path.join(desktopRoot, 'build', 'native-deps', 'node_modules')
  if (!fs.existsSync(src)) {
    throw new Error(`[after-pack] Missing staged runtime modules at ${src}. Run scripts/stage-native-deps.cjs first.`)
  }
  const dst = path.join(resourcesDir, 'native-deps', 'node_modules')
  fs.rmSync(dst, { recursive: true, force: true })
  fs.mkdirSync(path.dirname(dst), { recursive: true })
  fs.cpSync(src, dst, { recursive: true, force: true })
  console.log(`[after-pack] copied staged runtime node_modules -> ${dst}`)
}

exports.default = async function afterPack(context) {
  const desktopRoot = path.resolve(__dirname, '..')
  copyStagedRuntimeModules(desktopRoot, resolvePackagedResourcesDir(context))

  if (context.electronPlatformName !== 'win32') {
    return
  }

  const productName = context.packager?.appInfo?.productFilename || 'Hermes'
  const exe = path.join(context.appOutDir, `${productName}.exe`)

  try {
    await stampExeIdentity(exe, desktopRoot)
  } catch (err) {
    // Never fail the build over a cosmetic stamp.
    console.warn(`[after-pack] exe identity stamp failed (${err.message}); Hermes.exe keeps the stock Electron icon`)
  }
}
