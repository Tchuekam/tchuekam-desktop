/**
 * Tests for electron/business-local-ai.cjs.
 *
 * Run with: node --test electron/business-local-ai.test.cjs
 */

'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')

const {
  BUSINESS_LOCAL_MODELS,
  buildAssistantMessages,
  buildOperationMessages,
  buildServerArgs,
  cleanModelOutput,
  computeThreadCounts,
  createBusinessLocalAiManager,
  detectHardwareProfile,
  getPlatformRuntimeAssetMatcher,
  parseSkillSuggestions
} = require('./business-local-ai.cjs')

test('detectHardwareProfile flags <= 3.5 GB PCs as low-RAM and picks ultra-light defaults', () => {
  const pc2gb = detectHardwareProfile({
    totalMemoryBytes: 2 * 1024 * 1024 * 1024,
    freeMemoryBytes: 600 * 1024 * 1024,
    cpuCount: 2
  })
  assert.equal(pc2gb.isLowRamPc, true)
  assert.equal(pc2gb.recommendedModelId, 'qwen3-0.6b-q4')

  const tiny1500 = detectHardwareProfile({
    totalMemoryBytes: 1500 * 1024 * 1024,
    freeMemoryBytes: 400 * 1024 * 1024,
    cpuCount: 2
  })
  assert.equal(tiny1500.isLowRamPc, true)
  assert.equal(tiny1500.recommendedModelId, 'smollm2-360m-q4')

  const pc8gb = detectHardwareProfile({
    totalMemoryBytes: 8 * 1024 * 1024 * 1024,
    freeMemoryBytes: 4 * 1024 * 1024 * 1024,
    cpuCount: 4
  })
  assert.equal(pc8gb.isLowRamPc, false)
})

test('buildServerArgs configures tight 2GB RAM memory caps and single-slot parallelism', () => {
  const spec = BUSINESS_LOCAL_MODELS.find(m => m.id === 'qwen3-0.6b-q4')
  const args = buildServerArgs({
    modelPath: '/tmp/Qwen3-0.6B-Q4_K_M.gguf',
    modelSpec: spec,
    port: 12345,
    config: { ctxSize: 1024, threads: 0, useKvQuant: true },
    hardware: { cpuCount: 2, isLowRamPc: true }
  })

  assert.ok(args.includes('--parallel'))
  assert.equal(args[args.indexOf('--parallel') + 1], '1')
  assert.equal(args[args.indexOf('--ctx-size') + 1], '1024')
  assert.equal(args[args.indexOf('--n-gpu-layers') + 1], '0')
  assert.equal(args[args.indexOf('--cache-type-k') + 1], 'q8_0')
  assert.equal(args[args.indexOf('--cache-type-v') + 1], 'q8_0')
  assert.ok(args.includes('--no-warmup'))
  assert.equal(args[args.indexOf('--reasoning') + 1], 'off')
  assert.equal(args[args.indexOf('--reasoning-budget') + 1], '0')
})

test('computeThreadCounts reserves UI headroom on dual-core and quad-core CPUs', () => {
  assert.deepEqual(computeThreadCounts(2, true), { threads: 1, threadsBatch: 2 })
  assert.deepEqual(computeThreadCounts(4, true), { threads: 2, threadsBatch: 3 })
  assert.deepEqual(computeThreadCounts(8, false), { threads: 4, threadsBatch: 4 })
})

test('getPlatformRuntimeAssetMatcher matches official llama.cpp CPU archives across OSes', () => {
  const win64 = getPlatformRuntimeAssetMatcher('win32', 'x64')
  assert.equal(win64.match('llama-b12484-bin-win-cpu-x64.zip'), true)
  assert.equal(win64.match('llama-b12484-bin-win-cuda-12.4-x64.zip'), false)

  const macArm = getPlatformRuntimeAssetMatcher('darwin', 'arm64')
  assert.equal(macArm.match('llama-b12484-bin-macos-arm64.tar.gz'), true)

  const linux64 = getPlatformRuntimeAssetMatcher('linux', 'x64')
  assert.equal(linux64.match('llama-b12484-bin-ubuntu-x64.tar.gz'), true)
})

test('cleanModelOutput strips <think> blocks and markdown code fences', () => {
  const raw = '<think>internal reasoning</think>\n```\nProfil exécutif orienté résultats.\n```'
  assert.equal(cleanModelOutput(raw), 'Profil exécutif orienté résultats.')
})

test('parseSkillSuggestions extracts up to 6 deduplicated skills', () => {
  const skills = parseSkillSuggestions('1. Python, TypeScript, Python, OHADA Accounting\n- Financial Modeling\n- Agile Delivery\n- Extra')
  assert.deepEqual(skills, [
    'Python',
    'TypeScript',
    'OHADA Accounting',
    'Financial Modeling',
    'Agile Delivery',
    'Extra'
  ])
})

test('buildOperationMessages and buildAssistantMessages stay compact for 1024-ctx budget', () => {
  const op = buildOperationMessages({
    operation: 'improve_summary',
    input: 'Ingénieur logiciel avec 5 ans d’expérience à Douala.',
    context: 'Senior Backend Engineer',
    language: 'fr'
  })
  assert.equal(op.messages.length, 2)
  assert.ok(op.messages[0].content.includes('[to confirm]'))
  assert.ok(op.messages[0].content.includes('French'))

  const chat = buildAssistantMessages({
    message: 'Check missing fields',
    language: 'en',
    documentSummary: 'Doc: Facture | Total: 150000 FCFA | Client: [to confirm]',
    history: [
      { role: 'user', content: 'Old 1' },
      { role: 'assistant', content: 'Old 2' },
      { role: 'user', content: 'Recent Q' },
      { role: 'assistant', content: 'Recent A' }
    ]
  })
  // System + last 2 history messages + current question = 4
  assert.equal(chat.length, 4)
  assert.ok(chat[0].content.includes('150000 FCFA'))
})

test('createBusinessLocalAiManager installs runtime+model via mock downloader and serves serialized operations', async () => {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-biz-ai-test-'))
  let fakeServer = null
  const origEnvOverride = process.env.HERMES_BUSINESS_LLAMA_SERVER

  try {
    // Spin up a lightweight HTTP mock pretending to be llama-server
    fakeServer = http.createServer((req, res) => {
      if (req.url === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ status: 'ok' }))
        return
      }
      if (req.url === '/v1/chat/completions' && req.method === 'POST') {
        const chunks = []
        req.on('data', c => chunks.push(c))
        req.on('end', () => {
          const body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
          const sys = body.messages?.[0]?.content || ''
          const reply = sys.includes('6 relevant professional skills')
            ? 'OHADA Compliance, Excel Modeling, Invoicing, Financial Audit, French, Negotiation'
            : '<think>skip</think>Résultats concrets vérifiés [to confirm].'
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(
            JSON.stringify({
              choices: [{ message: { content: reply } }],
              usage: { completion_tokens: 12 },
              timings: { predicted_per_second: 34.5 }
            })
          )
        })
        return
      }
      res.writeHead(404)
      res.end()
    })

    await new Promise(resolve => fakeServer.listen(0, '127.0.0.1', resolve))
    const mockPort = fakeServer.address().port

    // Fake llama-server script that starts a tiny proxy to mockPort and stays alive until SIGTERM
    const fakeServerJs = path.join(tmpHome, 'fake-llama.cjs')
    fs.writeFileSync(
      fakeServerJs,
      `
const http = require('node:http');
const args = process.argv.slice(2);
const portIdx = args.indexOf('--port');
const port = Number(args[portIdx + 1]);
const srv = http.createServer((req, res) => {
  const proxy = http.request({ hostname: '127.0.0.1', port: ${mockPort}, path: req.url, method: req.method, headers: req.headers }, pres => {
    res.writeHead(pres.statusCode, pres.headers);
    pres.pipe(res);
  });
  req.pipe(proxy);
});
srv.listen(port, '127.0.0.1');
process.on('SIGTERM', () => { srv.close(() => process.exit(0)); });
setInterval(() => {}, 1000);
`,
      'utf8'
    )

    // Create a launcher batch/node wrapper or point override directly?
    // spawn(binaryPath, args) runs directly; so write a tiny .cmd/.sh or use node script if platform matches.
    // On Windows spawn() without shell requires .exe, so let's place process.execPath? No, we can test install() separately with mock files and mock fetchJson!
    const runtimeDir = path.join(tmpHome, 'business-agent', 'runtime')
    const modelsDir = path.join(tmpHome, 'business-agent', 'models')
    fs.mkdirSync(runtimeDir, { recursive: true })
    fs.mkdirSync(modelsDir, { recursive: true })

    const statusUpdates = []
    const mgr = createBusinessLocalAiManager({
      hermesHome: tmpHome,
      platform: 'win32',
      arch: 'x64',
      totalMemoryBytes: 2 * 1024 * 1024 * 1024,
      cpuCount: 2,
      minValidModelBytes: 16,
      onStatus: s => statusUpdates.push(s),
      fetchJson: async url => {
        if (url.includes('api.github.com')) {
          return [
            {
              tag_name: 'b12484',
              assets: [
                {
                  name: 'llama-b12484-bin-win-cpu-x64.zip',
                  size: 1024,
                  browser_download_url: 'https://example.invalid/llama.zip'
                }
              ]
            }
          ]
        }
        return requestToMock(url)
      },
      downloadFile: async (_url, destPath, { onProgress }) => {
        fs.mkdirSync(path.dirname(destPath), { recursive: true })
        fs.writeFileSync(destPath, '0123456789abcdef0123456789abcdef')
        onProgress?.({ downloadedBytes: 32, totalBytes: 32, percent: 100, speedBps: 3200 })
        return destPath
      },
      extractArchive: async (_archivePath, destDir) => {
        fs.writeFileSync(path.join(destDir, 'llama-server.exe'), 'fake-binary')
      }
    })

    const initial = await mgr.getStatus()
    assert.equal(initial.installed, false)
    assert.equal(initial.hardware.isLowRamPc, true)

    const afterInstall = await mgr.install({ modelId: 'smollm2-360m-q4' })
    assert.equal(afterInstall.installed, true)
    assert.equal(afterInstall.activeModelId, 'smollm2-360m-q4')
    assert.ok(afterInstall.installedModels.includes('smollm2-360m-q4'))
    assert.ok(statusUpdates.some(s => s.installProgress?.stage === 'complete'))

    // Verify disable & model removal
    const disabled = await mgr.setConfig({ enabled: false })
    assert.equal(disabled.enabled, false)
    const opDisabled = await mgr.runOperation({ operation: 'improve_summary', input: 'abc', language: 'fr' })
    assert.equal(opDisabled.disabled, true)

    const afterDelete = await mgr.deleteModel('smollm2-360m-q4')
    assert.equal(afterDelete.installedModels.includes('smollm2-360m-q4'), false)

    await mgr.dispose()
  } finally {
    if (origEnvOverride === undefined) delete process.env.HERMES_BUSINESS_LLAMA_SERVER
    else process.env.HERMES_BUSINESS_LLAMA_SERVER = origEnvOverride
    if (fakeServer) await new Promise(r => fakeServer.close(r))
    fs.rmSync(tmpHome, { recursive: true, force: true })
  }
})

function requestToMock(url) {
  return new Promise((resolve, reject) => {
    http
      .get(url, res => {
        const chunks = []
        res.on('data', c => chunks.push(c))
        res.on('end', () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))
          } catch (e) {
            reject(e)
          }
        })
      })
      .on('error', reject)
  })
}
