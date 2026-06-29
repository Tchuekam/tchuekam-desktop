/**
 * Tests for scripts/stage-native-deps.cjs (the JS-dep staging path) and
 * scripts/verify-runtime-deps.cjs.
 *
 * Run with: node --test scripts/stage-native-deps.test.cjs
 * (Wired into npm test:desktop:platforms in package.json.)
 *
 * These guard the electron-updater regression: a main-process runtime dep that
 * is declared but not staged into resources must be caught at build time, and
 * the staged tree must be self-contained (require()-able with no leakage to the
 * workspace node_modules).
 */

const test = require('node:test')
const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const APP_ROOT = path.resolve(__dirname, '..')
const STAGE_ROOT = path.join(APP_ROOT, 'build', 'native-deps')
const JS_STAGE = path.join(STAGE_ROOT, 'node_modules')
const NODE = process.execPath

function runStaging() {
  execFileSync(NODE, ['scripts/stage-native-deps.cjs'], { cwd: APP_ROOT, stdio: 'pipe' })
}

test('staging produces a self-contained electron-updater tree', () => {
  runStaging()
  const euDir = path.join(JS_STAGE, 'electron-updater')
  assert.ok(fs.existsSync(path.join(euDir, 'package.json')), 'electron-updater staged')

  // Load it from a clean child process whose only module root is the staged
  // tree itself (cwd = a temp dir, no node_modules). Proves the transitive
  // closure was staged — if any dep were missing this require would throw.
  const script = `require(${JSON.stringify(euDir)}); console.log('ok')`
  const out = execFileSync(NODE, ['-e', script], {
    cwd: require('node:os').tmpdir(),
    stdio: 'pipe'
  }).toString()
  assert.match(out, /ok/)
})

test('verify-runtime-deps passes against a correctly staged tree', () => {
  runStaging()
  // Exit 0 == contract satisfied.
  assert.doesNotThrow(() =>
    execFileSync(NODE, ['scripts/verify-runtime-deps.cjs'], { cwd: APP_ROOT, stdio: 'pipe' })
  )
})

test('verify-runtime-deps FAILS the build when a runtime dep is unstaged', () => {
  runStaging()
  const euDir = path.join(JS_STAGE, 'electron-updater')
  const tmp = path.join(STAGE_ROOT, '__eu_moved__')
  fs.rmSync(tmp, { recursive: true, force: true })
  fs.renameSync(euDir, tmp)
  try {
    assert.throws(
      () => execFileSync(NODE, ['scripts/verify-runtime-deps.cjs'], { cwd: APP_ROOT, stdio: 'pipe' }),
      /Command failed/,
      'expected non-zero exit when electron-updater is not staged'
    )
  } finally {
    // Restore so a developer's working tree isn't left half-staged.
    fs.renameSync(tmp, euDir)
  }
})
