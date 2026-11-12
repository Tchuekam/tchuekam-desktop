'use strict'

/**
 * Tests for stage-app-deps.cjs.
 *
 * The v1.0.0 installer shipped without electron-updater and died at startup
 * with "Cannot find module". npm workspaces had hoisted the module to the repo
 * root, where electron-builder's app-relative `files` glob could not see it.
 *
 * What matters here is that the resolver finds a module wherever the workspace
 * put it, and that it follows the whole dependency chain -- the old config
 * named only electron-updater and builder-util-runtime, so even a build that
 * found them would have crashed on fs-extra.
 */

const assert = require('node:assert')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { test } = require('node:test')

const { resolveClosure, moduleDir } = require('./stage-app-deps.cjs')

function fixture(modules) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'stage-app-deps-'))
  for (const [where, manifest] of Object.entries(modules)) {
    const dir = path.join(root, where)
    fs.mkdirSync(dir, { recursive: true })
    fs.writeFileSync(path.join(dir, 'package.json'), JSON.stringify(manifest))
    fs.writeFileSync(path.join(dir, 'index.js'), 'module.exports = {}\n')
  }
  return root
}

test('finds a module hoisted to the workspace root', () => {
  const root = fixture({ 'root_modules/electron-updater': { name: 'electron-updater' } })
  const roots = [path.join(root, 'app_modules'), path.join(root, 'root_modules')]

  assert.ok(moduleDir('electron-updater', roots), 'hoisted module should be found')
})

test('prefers a module nested under the app over the hoisted copy', () => {
  // Node resolves the nearest copy first; staging must agree or the packaged
  // app runs different code than development did.
  const root = fixture({
    'app_modules/semver': { name: 'semver', version: '7.0.0' },
    'root_modules/semver': { name: 'semver', version: '6.0.0' },
  })
  const roots = [path.join(root, 'app_modules'), path.join(root, 'root_modules')]

  assert.strictEqual(moduleDir('semver', roots), path.join(root, 'app_modules', 'semver'))
})

test('follows the whole dependency chain, not just the named entry point', () => {
  const root = fixture({
    'root_modules/electron-updater': { name: 'electron-updater', dependencies: { 'fs-extra': '*' } },
    'root_modules/fs-extra': { name: 'fs-extra', dependencies: { 'graceful-fs': '*' } },
    'root_modules/graceful-fs': { name: 'graceful-fs' },
  })
  const roots = [path.join(root, 'root_modules')]

  const { found, missing } = resolveClosure(['electron-updater'], roots)

  assert.deepStrictEqual(missing, [])
  assert.deepStrictEqual(
    [...found.keys()].sort(),
    ['electron-updater', 'fs-extra', 'graceful-fs'],
    'a transitive dependency left behind crashes the app just as hard'
  )
})

test('reports a dependency that is not installed instead of staging a broken tree', () => {
  const root = fixture({
    'root_modules/electron-updater': { name: 'electron-updater', dependencies: { 'fs-extra': '*' } },
  })
  const roots = [path.join(root, 'root_modules')]

  const { missing } = resolveClosure(['electron-updater'], roots)

  assert.deepStrictEqual(missing, ['fs-extra'])
})

test('a missing optional dependency is not a failure', () => {
  const root = fixture({
    'root_modules/electron-updater': {
      name: 'electron-updater',
      optionalDependencies: { 'not-installed': '*' },
    },
  })
  const roots = [path.join(root, 'root_modules')]

  const { found, missing } = resolveClosure(['electron-updater'], roots)

  assert.deepStrictEqual(missing, [])
  assert.deepStrictEqual([...found.keys()], ['electron-updater'])
})

test('a dependency cycle terminates', () => {
  const root = fixture({
    'root_modules/a': { name: 'a', dependencies: { b: '*' } },
    'root_modules/b': { name: 'b', dependencies: { a: '*' } },
  })
  const roots = [path.join(root, 'root_modules')]

  const { found } = resolveClosure(['a'], roots)

  assert.deepStrictEqual([...found.keys()].sort(), ['a', 'b'])
})
