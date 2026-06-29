'use strict'

/**
 * Stage native node-modules dependencies for electron-builder packaging.
 *
 * Workspace dedup hoists `node-pty` into the root `node_modules/`, which
 * electron-builder's default file collector (when `files:` is explicitly set
 * in package.json) cannot reach.  The result: packaged builds ship with no
 * .node binaries and PTY initialization fails at runtime ("PTY support is
 * unavailable").
 *
 * Rather than restructure the workspace dedup (would require nohoist /
 * package.json shenanigans and risk breaking dev) or balloon the package
 * with the whole node_modules tree, we copy ONLY the runtime-essential
 * files of the native dep into apps/desktop/build/native-deps/ and ship
 * THAT subtree via extraResources.  main.cjs falls back to require()-ing
 * from process.resourcesPath when the hoisted-root require fails.
 *
 * Runs as part of `npm run build`. Idempotent -- always re-stages on each
 * build to pick up native binary updates.
 *
 * Layout note: upstream node-pty (microsoft/node-pty 1.x) is N-API based
 * and ships its prebuilts under `prebuilds/<platform>-<arch>/` instead of
 * `build/Release/`.  Its runtime resolver (lib/utils.js) checks
 * build/Release first and falls through to the per-arch prebuilds dir, so
 * shipping only the latter is sufficient for packaged runs.  Per-arch
 * staging keeps the resource bundle lean -- we only need the target
 * arch's prebuilt, not all of them.
 */

const fs = require('node:fs')
const path = require('node:path')

const APP_ROOT = path.resolve(__dirname, '..')
const REPO_ROOT = path.resolve(APP_ROOT, '..', '..')
const STAGE_ROOT = path.join(APP_ROOT, 'build', 'native-deps')

// The target arch may be overridden by electron-builder via npm_config_arch
// (e.g. `npm run dist -- --arm64`); fall back to the build host's arch.
const TARGET_ARCH = process.env.npm_config_arch || process.arch
const TARGET_PLATFORM = process.platform

// Modules to stage. The "from" path is the hoisted location in the workspace
// root; "to" is the layout we want inside build/native-deps/.  The "include"
// globs (relative to "from") select the runtime-essential files.  Anything
// outside the include list is left behind (source, deps/, scripts/, etc.).
const NATIVE_DEPS = [
  {
    from: path.join(REPO_ROOT, 'node_modules', 'node-pty'),
    to: path.join(STAGE_ROOT, 'node-pty'),
    include: [
      'package.json',
      'lib/*.js',
      'lib/**/*.js',
      'build/Release/*.node',
      // Per-arch runtime payload. Explicit file types so we don't ship the
      // ~25 MB of .pdb debug symbols that prebuild-install bundles for
      // Windows crash analysis -- not used at runtime, would just bloat
      // the installer.
      `prebuilds/${TARGET_PLATFORM}-${TARGET_ARCH}/*.node`,
      `prebuilds/${TARGET_PLATFORM}-${TARGET_ARCH}/*.dll`,
      `prebuilds/${TARGET_PLATFORM}-${TARGET_ARCH}/*.exe`,
      `prebuilds/${TARGET_PLATFORM}-${TARGET_ARCH}/spawn-helper`,
      `prebuilds/${TARGET_PLATFORM}-${TARGET_ARCH}/conpty/*`
    ]
  }
]

// Pure-JS main-process runtime dependencies. Unlike node-pty (a native dep
// staged file-by-file), these are required by the Electron MAIN process at
// runtime and pull in a transitive dependency tree of their own. Because
// before-build.cjs returns false (electron-builder's node_modules collector
// is disabled) and the `files:` allowlist omits node_modules, NOTHING from
// node_modules reaches the asar. So any main-process dependency must be staged
// here and require()'d back from process.resourcesPath at runtime.
//
// We stage each root into a flat `node_modules/` directory that mirrors npm's
// hoisted layout, then resolve its full production dependency closure from the
// workspace root and copy each package in. main.cjs / auto-updater.cjs fall
// back to require()-ing from `<resources>/native-deps/node_modules/<name>`
// when the normal (dev / hoisted) require fails.
//
// electron-updater is the concrete case that motivated this: it was added to
// dependencies but never staged, so packaged builds crashed at startup with
// "Cannot find module 'electron-updater'".
const JS_DEP_ROOTS = ['electron-updater']
const JS_DEPS_STAGE = path.join(STAGE_ROOT, 'node_modules')

function rmrf(target) {
  fs.rmSync(target, { recursive: true, force: true })
}

function ensureDir(target) {
  fs.mkdirSync(target, { recursive: true })
}

function walk(root) {
  const results = []
  const stack = [root]
  while (stack.length) {
    const current = stack.pop()
    let entries
    try {
      entries = fs.readdirSync(current, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) {
        stack.push(full)
      } else if (entry.isFile()) {
        results.push(full)
      }
    }
  }
  return results
}

// Match a relative path against simple ** and * glob patterns. Implementation
// is intentionally tiny -- the include lists are small and don't need full
// minimatch support.
function matchGlob(rel, pattern) {
  const r = rel.replace(/\\/g, '/')
  const re = new RegExp(
    '^' +
      pattern
        .replace(/\\/g, '/')
        .replace(/[.+^${}()|[\]\\]/g, '\\$&')
        .replace(/\*\*/g, '__DOUBLE_STAR__')
        .replace(/\*/g, '[^/]*')
        .replace(/__DOUBLE_STAR__/g, '.*') +
      '$'
  )
  return re.test(r)
}

function stageOne(spec) {
  if (!fs.existsSync(spec.from)) {
    throw new Error(
      `stage-native-deps: source missing at ${spec.from}.  Run \`npm install\` ` +
        `at the workspace root first.`
    )
  }
  rmrf(spec.to)
  ensureDir(spec.to)

  const files = walk(spec.from)
  let copied = 0
  for (const abs of files) {
    const rel = path.relative(spec.from, abs)
    const included = spec.include.some(g => matchGlob(rel, g))
    if (!included) continue
    const dest = path.join(spec.to, rel)
    ensureDir(path.dirname(dest))
    fs.copyFileSync(abs, dest)
    // node-pty's darwin spawn-helper and the Windows helper binaries
    // (OpenConsole.exe, winpty-agent.exe) are invoked via posix_spawn /
    // CreateProcess at runtime, so they must remain executable in the
    // staged tree.  fs.copyFileSync preserves source mode on POSIX, but we
    // re-assert +x defensively for the darwin spawn-helper (no extension
    // means a stripped mode would be silently broken at runtime).
    if (path.basename(rel) === 'spawn-helper' && process.platform !== 'win32') {
      try { fs.chmodSync(dest, 0o755) } catch { /* best-effort */ }
    }
    copied += 1
  }
  console.log(`[stage-native-deps] ${path.relative(APP_ROOT, spec.to)}: ${copied} files`)
}

// Resolve a package directory by walking the node_modules chain upward from
// `fromDir`, mirroring Node's own resolution. Returns the absolute package
// directory, or null if not found.
function resolvePackageDir(name, fromDir) {
  let dir = fromDir
  // Guard against symlink/loop pathologies with a depth cap.
  for (let i = 0; i < 64; i++) {
    const candidate = path.join(dir, 'node_modules', name)
    if (fs.existsSync(path.join(candidate, 'package.json'))) {
      return candidate
    }
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return null
}

// Copy a whole package directory into the staged flat node_modules, excluding
// its own nested node_modules (transitive deps are resolved and staged
// separately so the flat layout stays npm-hoist-compatible).
function copyPackage(srcDir, destDir) {
  ensureDir(destDir)
  const stack = [srcDir]
  while (stack.length) {
    const current = stack.pop()
    let entries
    try {
      entries = fs.readdirSync(current, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      if (entry.name === 'node_modules') continue
      const abs = path.join(current, entry.name)
      const rel = path.relative(srcDir, abs)
      const dest = path.join(destDir, rel)
      if (entry.isDirectory()) {
        stack.push(abs)
      } else if (entry.isFile()) {
        ensureDir(path.dirname(dest))
        fs.copyFileSync(abs, dest)
      }
    }
  }
}

// Stage a pure-JS dependency and its full production dependency closure into
// JS_DEPS_STAGE (a flat node_modules). `staged` tracks names already copied so
// shared transitive deps aren't duplicated and cycles terminate.
function stageJsTree(name, fromDir, staged) {
  if (staged.has(name)) return
  const pkgDir = resolvePackageDir(name, fromDir)
  if (!pkgDir) {
    throw new Error(
      `stage-native-deps: runtime dependency '${name}' not found under any ` +
        `node_modules from ${fromDir}. Run \`npm install\` at the workspace root.`
    )
  }
  staged.add(name)
  copyPackage(pkgDir, path.join(JS_DEPS_STAGE, name))

  let pkgJson
  try {
    pkgJson = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'))
  } catch {
    return
  }
  const deps = Object.keys(pkgJson.dependencies || {})
  for (const dep of deps) {
    // Resolve transitive deps starting from this package's own location so a
    // nested (non-hoisted) version is preferred when present.
    stageJsTree(dep, pkgDir, staged)
  }
}

function stageJsRoots() {
  if (JS_DEP_ROOTS.length === 0) return
  const staged = new Set()
  for (const root of JS_DEP_ROOTS) {
    stageJsTree(root, APP_ROOT, staged)
  }
  console.log(
    `[stage-native-deps] node_modules: ${staged.size} packages ` +
      `(${[...JS_DEP_ROOTS].join(', ')} + transitive)`
  )
}

function main() {
  rmrf(STAGE_ROOT)
  ensureDir(STAGE_ROOT)
  for (const spec of NATIVE_DEPS) {
    stageOne(spec)
  }
  stageJsRoots()
}

main()
