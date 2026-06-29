'use strict'

/**
 * verify-runtime-deps.cjs — packaging regression guard.
 *
 * The Electron MAIN process needs a small set of runtime node modules at
 * launch. Packaged builds ship NO node_modules in the asar (before-build.cjs
 * returns false, disabling electron-builder's collector; the `files:`
 * allowlist omits node_modules). Those deps are instead staged into
 * build/native-deps/ by stage-native-deps.cjs and require()'d back from
 * process.resourcesPath at runtime.
 *
 * If a main-process dep is added to package.json but NOT staged, the app
 * crashes on first launch with "Cannot find module '<dep>'" — exactly the
 * electron-updater regression this script exists to prevent.
 *
 * This runs as part of `npm run build` (after staging, before tsc/vite). It
 * FAILS THE BUILD if any contracted runtime dep is:
 *   - not declared in package.json `dependencies`, or
 *   - not present in the staged tree, or
 *   - not actually loadable (require throws / missing transitive dep).
 *
 * To add a new main-process runtime dependency: add it to `dependencies`,
 * stage it (NATIVE_DEPS or JS_DEP_ROOTS in stage-native-deps.cjs), and list it
 * here.
 */

const fs = require('node:fs')
const path = require('node:path')

const APP_ROOT = path.resolve(__dirname, '..')
const STAGE_ROOT = path.join(APP_ROOT, 'build', 'native-deps')
const JS_STAGE = path.join(STAGE_ROOT, 'node_modules')

const TARGET_ARCH = process.env.npm_config_arch || process.arch
const TARGET_PLATFORM = process.platform

// The runtime-dependency contract for the Electron main process.
//   kind 'js'     -> staged as a flat node_modules tree; must require() cleanly.
//   kind 'native' -> staged file-by-file; must have a prebuilt binary for the
//                    target platform/arch.
const CONTRACT = [
  { name: 'electron-updater', kind: 'js' },
  { name: 'node-pty', kind: 'native' }
]

const errors = []

function pkgDependencies() {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'package.json'), 'utf8'))
    return pkg.dependencies || {}
  } catch (err) {
    errors.push(`could not read package.json: ${err.message}`)
    return {}
  }
}

function verifyJs(name) {
  const dir = path.join(JS_STAGE, name)
  if (!fs.existsSync(path.join(dir, 'package.json'))) {
    errors.push(`'${name}' is not staged at ${path.relative(APP_ROOT, dir)} (run stage-native-deps.cjs)`)
    return
  }
  // Prove the staged tree is self-contained: require it and all its transitive
  // deps resolve from the staged flat node_modules, with no leakage to the
  // workspace's own node_modules.
  try {
    require(dir)
  } catch (err) {
    errors.push(`'${name}' failed to load from the staged tree: ${err.message}`)
  }
}

function verifyNative(name) {
  const dir = path.join(STAGE_ROOT, name)
  if (!fs.existsSync(path.join(dir, 'package.json'))) {
    errors.push(`'${name}' is not staged at ${path.relative(APP_ROOT, dir)} (run stage-native-deps.cjs)`)
    return
  }
  // Must carry a runtime binary for the target platform/arch (build/Release or
  // the N-API per-arch prebuilds dir).
  const hasBinary =
    globHasNode(path.join(dir, 'build', 'Release')) ||
    globHasNode(path.join(dir, 'prebuilds', `${TARGET_PLATFORM}-${TARGET_ARCH}`))
  if (!hasBinary) {
    errors.push(
      `'${name}' has no native binary for ${TARGET_PLATFORM}-${TARGET_ARCH} in the staged tree`
    )
  }
}

function globHasNode(dir) {
  try {
    return fs.readdirSync(dir).some(f => f.endsWith('.node'))
  } catch {
    return false
  }
}

function main() {
  const deps = pkgDependencies()

  for (const item of CONTRACT) {
    if (!deps[item.name]) {
      errors.push(
        `'${item.name}' is a main-process runtime dependency but is missing from ` +
          `package.json "dependencies"`
      )
    }
    if (item.kind === 'js') verifyJs(item.name)
    else verifyNative(item.name)
  }

  if (errors.length) {
    console.error('\n[verify-runtime-deps] FAILED — packaged build would crash at launch:')
    for (const e of errors) console.error(`  ✗ ${e}`)
    console.error(
      '\nFix: declare the dependency in package.json, stage it in ' +
        'scripts/stage-native-deps.cjs, and list it in the CONTRACT in ' +
        'scripts/verify-runtime-deps.cjs.\n'
    )
    process.exit(1)
  }

  console.log(
    `[verify-runtime-deps] OK — ${CONTRACT.length} main-process runtime deps staged and loadable`
  )
}

main()
