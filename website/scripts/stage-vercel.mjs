#!/usr/bin/env node
// Stage the Docusaurus build for a Vercel service mounted at /docs.
//
// docusaurus.config.ts sets `baseUrl: '/docs/'`, so every emitted asset URL is
// absolute and prefixed: /docs/assets/js/main.*.js. A Vercel service rewrite
// forwards the matched path unchanged, so the service is asked for
// /docs/assets/... — but `npm run build` puts those files at the root of
// build/. Nesting the output under docs/ makes the served paths line up with
// the URLs Docusaurus already wrote into the HTML.
//
// If the docs ever move to the root of their own domain, drop this step and
// set baseUrl back to '/'.
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const build = join(root, 'build')
const staged = join(root, 'build-vercel')

if (!existsSync(build)) {
  console.error(`[website] No build/ directory at ${build} — run the docusaurus build first.`)
  process.exit(1)
}

rmSync(staged, { recursive: true, force: true })
mkdirSync(staged, { recursive: true })
cpSync(build, join(staged, 'docs'), { recursive: true })

console.log(`[website] Staged build/ -> build-vercel/docs/ for the /docs mount.`)
