'use strict'

/**
 * Stage pure-JS runtime dependencies for electron-builder packaging.
 *
 * Same root cause as stage-native-deps.cjs, different victim.  npm workspaces
 * hoist shared dependencies into the repo-root `node_modules/`, but
 * electron-builder resolves the `files:` globs in package.json relative to the
 * app directory.  So `node_modules/electron-updater/**` looks for
 * `apps/desktop/node_modules/electron-updater/` -- which does not exist -- and
 * silently matches nothing.  `beforeBuild` returns false, which switches off
 * electron-builder's own node_modules collector, so nothing else catches it.
 *
 * The v1.0.0 installer shipped with no node_modules in its asar at all.
 * `electron/auto-updater.cjs` ran `require('electron-updater')` at load, the
 * module was not there, and the main process died before a window opened:
 *
 *     A JavaScript error occurred in the main process
 *     Error: Cannot find module 'electron-updater'
 *
 * A glob that matches nothing is not an error, so the build stayed green all
 * the way to the customer.
 *
 * This copies each listed module AND its transitive runtime dependencies into
 * `build/app-node-modules/`, which package.json ships into the asar as
 * `node_modules/`.  Plain `require('electron-updater')` then resolves the
 * normal way: Node walks up from `app.asar/electron/` and finds
 * `app.asar/node_modules/`.
 *
 * Runs as part of `npm run build`.  Idempotent.
 */

const fs = require('node:fs')
const path = require('node:path')

const APP_ROOT = path.resolve(__dirname, '..')
const REPO_ROOT = path.resolve(APP_ROOT, '..', '..')
const STAGE_ROOT = path.join(APP_ROOT, 'build', 'app-node-modules')

// Modules the packaged main process requires by name. Their dependencies are
// resolved automatically, so this list only names the entry points.
const RUNTIME_MODULES = ['electron-updater']

// Where a workspace install may put a module. Order matters: a module nested
// under the app wins over the hoisted copy, matching Node's own resolution.
const SEARCH_ROOTS = [
  path.join(APP_ROOT, 'node_modules'),
  path.join(REPO_ROOT, 'node_modules'),
]

// Files that exist only for humans or for building from source. Dropping them
// keeps the installer lean without touching anything require() needs.
const SKIP_DIRS = new Set(['test', 'tests', '__tests__', 'example', 'examples', 'docs', '.bin', '.github'])
const SKIP_EXTENSIONS = new Set(['.md', '.markdown', '.map', '.ts.map', '.yml', '.yaml'])

function moduleDir(name, roots = SEARCH_ROOTS) {
  for (const root of roots) {
    const candidate = path.join(root, ...name.split('/'))
    if (fs.existsSync(path.join(candidate, 'package.json'))) return candidate
  }
  return null
}

function readManifest(dir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'))
  } catch {
    return {}
  }
}

/**
 * Every module the entry points need at runtime, entry points included.
 *
 * Only `dependencies` are followed. devDependencies are not installed in a
 * production tree, and optionalDependencies may legitimately be absent, so a
 * missing optional one is skipped rather than failing the build.
 */
function resolveClosure(entryNames, roots = SEARCH_ROOTS) {
  const found = new Map()
  const missing = []
  const queue = [...entryNames.map((name) => ({ name, required: true }))]

  while (queue.length) {
    const { name, required } = queue.shift()
    if (found.has(name)) continue

    const dir = moduleDir(name, roots)
    if (!dir) {
      if (required) missing.push(name)
      continue
    }

    found.set(name, dir)
    const manifest = readManifest(dir)
    for (const dep of Object.keys(manifest.dependencies || {})) {
      queue.push({ name: dep, required: true })
    }
    for (const dep of Object.keys(manifest.optionalDependencies || {})) {
      queue.push({ name: dep, required: false })
    }
  }

  return { found, missing }
}

function copyModule(from, to) {
  let copied = 0
  const stack = ['']
  while (stack.length) {
    const rel = stack.pop()
    const src = path.join(from, rel)
    let entries
    try {
      entries = fs.readdirSync(src, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      const childRel = path.join(rel, entry.name)
      if (entry.isDirectory()) {
        // A nested node_modules is a real resolution path, so it is kept.
        if (SKIP_DIRS.has(entry.name)) continue
        stack.push(childRel)
        continue
      }
      if (!entry.isFile()) continue
      if (SKIP_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) continue
      const dest = path.join(to, childRel)
      fs.mkdirSync(path.dirname(dest), { recursive: true })
      fs.copyFileSync(path.join(from, childRel), dest)
      copied += 1
    }
  }
  return copied
}

function main() {
  fs.rmSync(STAGE_ROOT, { recursive: true, force: true })
  fs.mkdirSync(STAGE_ROOT, { recursive: true })

  const { found, missing } = resolveClosure(RUNTIME_MODULES)

  if (missing.length) {
    throw new Error(
      `stage-app-deps: cannot find ${missing.join(', ')} in any of:\n` +
        SEARCH_ROOTS.map((r) => `  ${r}`).join('\n') +
        `\nRun \`npm install\` at the workspace root first. Packaging without ` +
        `these modules produces an app that dies at startup with ` +
        `"Cannot find module".`
    )
  }

  let files = 0
  for (const [name, dir] of found) {
    files += copyModule(dir, path.join(STAGE_ROOT, ...name.split('/')))
  }

  console.log(
    `[stage-app-deps] ${found.size} module(s), ${files} files -> ` +
      `${path.relative(APP_ROOT, STAGE_ROOT)}`
  )
  console.log(`[stage-app-deps] ${[...found.keys()].sort().join(', ')}`)
}

// Guarded so the resolver can be unit-tested without staging anything,
// matching write-build-stamp.cjs.
if (require.main === module) {
  main()
}

module.exports = { resolveClosure, moduleDir, RUNTIME_MODULES, SEARCH_ROOTS }
