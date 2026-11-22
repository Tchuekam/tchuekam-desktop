'use strict'

const fs = require('node:fs')
const fsp = require('node:fs/promises')
const http = require('node:http')
const https = require('node:https')
const net = require('node:net')
const os = require('node:os')
const path = require('node:path')
const { execFile, spawn } = require('node:child_process')

const DEFAULT_IDLE_UNLOAD_MS = 180_000
const DEFAULT_INFERENCE_TIMEOUT_MS = 45_000
const HEALTH_POLL_INTERVAL_MS = 200
const HEALTH_WAIT_TIMEOUT_MS = 25_000
const MEMORY_CACHE_TTL_MS = 4_000
const MAX_REDIRECTS = 6
const MIN_VALID_MODEL_BYTES = 50 * 1024 * 1024

const BUSINESS_LOCAL_MODELS = Object.freeze([
  {
    id: 'qwen3-0.6b-q4',
    name: 'Qwen3 0.6B (2GB FR/EN)',
    filename: 'Qwen3-0.6B-Q4_K_M.gguf',
    downloadUrl:
      'https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf?download=true',
    sizeMb: 378,
    estimatedRamMb: 400,
    minRamGb: 2,
    languages: 'FR / EN',
    recommendedForLowRam: true,
    reasoningModel: true,
    defaultCtxSize: 1024,
    summary: 'Recommended FR/EN bilingual model (~385 MB private RAM, ~20 tok/s on CPU).'
  },
  {
    id: 'smollm2-360m-q4',
    name: 'SmolLM2 360M (Micro 2GB)',
    filename: 'SmolLM2-360M-Instruct-Q4_K_M.gguf',
    downloadUrl:
      'https://huggingface.co/bartowski/SmolLM2-360M-Instruct-GGUF/resolve/main/SmolLM2-360M-Instruct-Q4_K_M.gguf?download=true',
    sizeMb: 258,
    estimatedRamMb: 335,
    minRamGb: 2,
    languages: 'EN (Ultra-Fast)',
    recommendedForLowRam: false,
    reasoningModel: false,
    defaultCtxSize: 1024,
    summary: 'Smallest footprint (~125 MB private / ~335 MB WS). Best for strict 2 GB English PCs.'
  },
  {
    id: 'qwen2.5-0.5b-q4',
    name: 'Qwen2.5 0.5B Instruct (FR/EN)',
    filename: 'qwen2.5-0.5b-instruct-q4_k_m.gguf',
    downloadUrl:
      'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf?download=true',
    sizeMb: 469,
    estimatedRamMb: 550,
    minRamGb: 2,
    languages: 'FR / EN',
    recommendedForLowRam: false,
    reasoningModel: false,
    defaultCtxSize: 1024,
    summary: 'Classic compact FR/EN instruction model with low latency.'
  },
  {
    id: 'gemma3-1b-q4',
    name: 'Gemma 3 1B (4GB+ RAM)',
    filename: 'gemma-3-1b-it-Q4_K_M.gguf',
    downloadUrl:
      'https://huggingface.co/unsloth/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf?download=true',
    sizeMb: 769,
    estimatedRamMb: 1050,
    minRamGb: 4,
    languages: 'FR / EN',
    recommendedForLowRam: false,
    reasoningModel: false,
    defaultCtxSize: 1536,
    summary: 'Higher drafting quality for 4 GB+ RAM PCs (too heavy for 2 GB PCs).'
  }
])

const MODEL_BY_ID = new Map(BUSINESS_LOCAL_MODELS.map(model => [model.id, model]))

function getModelSpec(modelId) {
  return MODEL_BY_ID.get(modelId) || BUSINESS_LOCAL_MODELS[0]
}

function detectHardwareProfile(opts = {}) {
  const totalBytes = Number.isFinite(opts.totalMemoryBytes) ? opts.totalMemoryBytes : os.totalmem()
  const freeBytes = Number.isFinite(opts.freeMemoryBytes) ? opts.freeMemoryBytes : os.freemem()
  const cpuCount = Math.max(1, Number.isFinite(opts.cpuCount) ? Math.round(opts.cpuCount) : os.cpus().length || 2)
  const totalRamMb = Math.max(512, Math.round(totalBytes / (1024 * 1024)))
  const freeRamMb = Math.max(128, Math.round(freeBytes / (1024 * 1024)))
  const isLowRamPc = totalRamMb <= 3584
  const recommendedModelId = totalRamMb <= 1800 ? 'smollm2-360m-q4' : 'qwen3-0.6b-q4'

  return {
    totalRamMb,
    freeRamMb,
    cpuCount,
    isLowRamPc,
    recommendedModelId
  }
}

function getPlatformRuntimeAssetMatcher(platform = process.platform, arch = process.arch) {
  if (platform === 'win32') {
    if (arch === 'arm64') {
      return {
        archiveType: 'zip',
        binaryName: 'llama-server.exe',
        match: name => /^llama-b\d+-bin-win-cpu-arm64\.zip$/i.test(name)
      }
    }
    return {
      archiveType: 'zip',
      binaryName: 'llama-server.exe',
      match: name => /^llama-b\d+-bin-win-cpu-x64\.zip$/i.test(name)
    }
  }

  if (platform === 'darwin') {
    if (arch === 'arm64') {
      return {
        archiveType: 'tar.gz',
        binaryName: 'llama-server',
        match: name => /^llama-b\d+-bin-macos-arm64\.tar\.gz$/i.test(name)
      }
    }
    return {
      archiveType: 'tar.gz',
      binaryName: 'llama-server',
      match: name => /^llama-b\d+-bin-macos-x64\.tar\.gz$/i.test(name)
    }
  }

  if (platform === 'linux' && arch === 'x64') {
    return {
      archiveType: 'tar.gz',
      binaryName: 'llama-server',
      match: name => /^llama-b\d+-bin-ubuntu-x64\.tar\.gz$/i.test(name)
    }
  }

  return null
}

function computeThreadCounts(cpuCount, isLowRamPc) {
  const safeCpus = Math.max(1, Number(cpuCount) || 2)
  if (safeCpus <= 2) {
    return { threads: 1, threadsBatch: safeCpus }
  }
  if (isLowRamPc) {
    return {
      threads: Math.min(2, safeCpus - 1),
      threadsBatch: Math.min(3, safeCpus)
    }
  }
  return {
    threads: Math.min(4, Math.max(2, safeCpus - 1)),
    threadsBatch: Math.min(4, safeCpus)
  }
}

function clampCtxSize(value, fallback = 1024) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback
  }
  return Math.max(512, Math.min(2048, Math.round(parsed)))
}

function buildServerArgs({ modelPath, modelSpec, port, config, hardware }) {
  const ctxSize = clampCtxSize(config?.ctxSize, modelSpec?.defaultCtxSize || 1024)
  const { threads, threadsBatch } = computeThreadCounts(
    Number(config?.threads) > 0 ? Number(config.threads) : hardware.cpuCount,
    hardware.isLowRamPc
  )

  const args = [
    '--host',
    '127.0.0.1',
    '--port',
    String(port),
    '-m',
    modelPath,
    '--ctx-size',
    String(ctxSize),
    '--parallel',
    '1',
    '--batch-size',
    '256',
    '--ubatch-size',
    '128',
    '--n-gpu-layers',
    '0',
    '--threads',
    String(threads),
    '--threads-batch',
    String(threadsBatch),
    '--no-warmup'
  ]

  if (config?.useKvQuant !== false) {
    args.push('--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0')
  }

  if (modelSpec?.reasoningModel) {
    args.push('--reasoning', 'off', '--reasoning-budget', '0')
  }

  return args
}

function cleanModelOutput(rawText) {
  let text = String(rawText || '')
  text = text.replace(/<think>[\s\S]*?<\/think>/gi, '')
  text = text.replace(/^\s*```[a-zA-Z0-9_-]*\s*\r?\n/, '').replace(/\r?\n```\s*$/, '')
  return text.trim()
}

function parseSkillSuggestions(rawText) {
  const cleaned = cleanModelOutput(rawText)
  if (!cleaned) return []

  const items = cleaned
    .split(/[,;\r\n]+/)
    .map(item => item.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim())
    .map(item => item.replace(/^["'`]+|["'`]+$/g, '').trim())
    .filter(item => item.length >= 2 && item.length <= 48 && !/\[?(?:to confirm|illegible)\]?/i.test(item))

  const seen = new Set()
  const unique = []
  for (const item of items) {
    const key = item.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(item)
    if (unique.length >= 6) break
  }
  return unique
}

const OPERATION_SPECS = Object.freeze({
  improve_summary: {
    maxTokens: 160,
    instruction: (langLabel, ctx) =>
      `Expand and polish this professional CV summary into 2-3 executive sentences in ${langLabel}. Keep every existing fact, acronym (like OHADA), city, and number. Target role: ${ctx || 'general'}.`
  },
  enhance_bullets: {
    maxTokens: 180,
    instruction: (langLabel, ctx) =>
      `Rewrite each resume achievement bullet in ${langLabel} starting with a strong action verb, one bullet per line (no numbering). Keep all numbers intact. Role: ${ctx || 'general'}.`
  },
  suggest_skills: {
    maxTokens: 90,
    skipGroundingRule: true,
    instruction: (langLabel, ctx) =>
      `Return 6 short skill keywords (1-3 words each) in ${langLabel} for this role, separated only by commas (no sentences, no parentheses, no numbering). Role: ${ctx || 'general'}.`
  },
  tailor_to_job: {
    maxTokens: 180,
    instruction: (langLabel, ctx) =>
      `Adapt this summary in ${langLabel} to highlight relevant keywords from the target job without inventing fake experience. Target job: ${(ctx || '').slice(0, 300)}.`
  },
  translate: {
    maxTokens: 180,
    instruction: (langLabel, _ctx) =>
      `Translate the user text into ${langLabel}, keeping the exact facts, numbers, dates, and [to confirm] tags.`
  },
  expand_section: {
    maxTokens: 200,
    instruction: (langLabel, ctx) =>
      `Expand this business plan section in ${langLabel} with 3-4 concise operational bullet points. Section: ${ctx || 'Business Plan'}.`
  },
  refine_slide: {
    maxTokens: 130,
    instruction: (langLabel, ctx) =>
      `Tighten these pitch deck slide points in ${langLabel} into 3-4 crisp bullets (<= 12 words each). Slide: ${ctx || 'Slide'}.`
  },
  polish_letter: {
    maxTokens: 200,
    instruction: (langLabel, ctx) =>
      `Polish this cover letter body in ${langLabel} for clarity and persuasive executive tone. Role: ${ctx || 'general'}.`
  },
  summarize_scan: {
    maxTokens: 150,
    instruction: (langLabel, ctx) =>
      `Summarize the key facts, names, dates, and amounts from this scanned text in ${langLabel} in 3-5 short lines. Source: ${ctx || 'scan'}.`
  }
})

function buildOperationMessages(req) {
  const targetLang = req?.targetLanguage || req?.language || 'fr'
  const langLabel = targetLang === 'fr' ? 'French' : 'English'
  const spec = OPERATION_SPECS[req?.operation] || {
    maxTokens: 160,
    instruction: lang => `Refine this business document text concisely in ${lang}.`
  }

  const groundingClause = spec.skipGroundingRule
    ? 'Output ONLY the comma-separated skills.'
    : 'Keep every real name, date, acronym, and number intact. If key info is missing, mark it [to confirm]. Output ONLY the updated text.'

  const system = `You are a concise Business Hub assistant. ${spec.instruction(langLabel, req?.context)} ${groundingClause}`

  const input = String(req?.input || '').trim().slice(0, 1400) || '[empty — draft concise template with [to confirm] placeholders]'

  return {
    maxTokens: spec.maxTokens,
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: input }
    ]
  }
}

function buildAssistantMessages(req) {
  const langLabel = req?.language === 'en' ? 'English' : 'French'
  const docSummary = String(req?.documentSummary || '').trim().slice(0, 420)
  const history = Array.isArray(req?.history) ? req.history.slice(-2) : []
  const question = String(req?.message || '').trim().slice(0, 800)

  const systemParts = [
    `You are TchuekaM Business Hub Local Agent (fast offline specialist for CV, OHADA FCFA invoices, quotes, contracts, pitch decks, business plans, letters, attestations, and scans).`,
    `Reply concisely in ${langLabel} (or match the user's language). Never invent amounts, dates, or names; mark missing facts [to confirm].`
  ]

  if (docSummary) {
    systemParts.push(`Active document context:\n${docSummary}`)
  }

  const messages = [{ role: 'system', content: systemParts.join('\n') }]

  for (const item of history) {
    if (!item || (item.role !== 'user' && item.role !== 'assistant')) continue
    const content = String(item.content || '').trim().slice(0, 350)
    if (content) {
      messages.push({ role: item.role, content })
    }
  }

  messages.push({ role: 'user', content: question })
  return messages
}

function pickFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address()
      const port = addr && typeof addr === 'object' ? addr.port : 0
      server.close(() => {
        if (port > 0) resolve(port)
        else reject(new Error('Could not bind an ephemeral localhost port.'))
      })
    })
  })
}

function requestJson(url, options = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url)
    const client = parsed.protocol === 'https:' ? https : http
    const bodyBuf = options.body === undefined ? undefined : Buffer.from(JSON.stringify(options.body), 'utf8')
    const timeoutMs = Number(options.timeoutMs) > 0 ? Number(options.timeoutMs) : 15_000

    const req = client.request(
      parsed,
      {
        method: options.method || 'GET',
        headers: {
          'User-Agent': 'tchuekam-desktop',
          ...(options.headers || {}),
          ...(bodyBuf
            ? {
                'Content-Type': 'application/json',
                'Content-Length': String(bodyBuf.length)
              }
            : {})
        }
      },
      res => {
        const chunks = []
        res.on('data', chunk => chunks.push(chunk))
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8')
          const status = res.statusCode || 500
          if (status >= 400) {
            reject(new Error(`HTTP ${status}: ${text.slice(0, 300)}`))
            return
          }
          if (!text) {
            resolve(null)
            return
          }
          try {
            resolve(JSON.parse(text))
          } catch (err) {
            reject(new Error(`Invalid JSON from ${url}: ${err.message}`))
          }
        })
      }
    )

    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`Request timed out after ${timeoutMs}ms`))
    })
    req.on('error', reject)
    if (bodyBuf) req.write(bodyBuf)
    req.end()
  })
}

function downloadFileWithProgress(url, destPath, { abortSignal, onProgress } = {}, redirectDepth = 0) {
  return new Promise((resolve, reject) => {
    if (abortSignal?.aborted) {
      reject(new Error('Download cancelled.'))
      return
    }

    const parsed = new URL(url)
    const client = parsed.protocol === 'https:' ? https : http
    const tmpPath = `${destPath}.part`
    fs.mkdirSync(path.dirname(destPath), { recursive: true })

    let settled = false
    let req = null
    let out = null

    const cleanupPartial = () => {
      try {
        if (out) out.close()
      } catch {}
    }

    const onAbort = () => {
      if (settled) return
      settled = true
      if (req) {
        try {
          req.destroy()
        } catch {}
      }
      cleanupPartial()
      reject(new Error('Download cancelled.'))
    }

    if (abortSignal) {
      abortSignal.addEventListener('abort', onAbort, { once: true })
    }

    const finishReject = err => {
      if (abortSignal) abortSignal.removeEventListener('abort', onAbort)
      if (settled) return
      settled = true
      cleanupPartial()
      reject(err)
    }

    req = client.get(
      parsed,
      {
        headers: { 'User-Agent': 'tchuekam-desktop' }
      },
      res => {
        const status = res.statusCode || 0
        if (status >= 300 && status < 400 && res.headers.location) {
          res.resume()
          if (abortSignal) abortSignal.removeEventListener('abort', onAbort)
          if (redirectDepth >= MAX_REDIRECTS) {
            finishReject(new Error(`Too many redirects downloading ${url}`))
            return
          }
          const nextUrl = new URL(res.headers.location, parsed).toString()
          settled = true
          downloadFileWithProgress(nextUrl, destPath, { abortSignal, onProgress }, redirectDepth + 1).then(
            resolve,
            reject
          )
          return
        }

        if (status !== 200) {
          res.resume()
          finishReject(new Error(`Download failed with HTTP ${status} for ${url}`))
          return
        }

        const totalBytes = Number(res.headers['content-length'] || 0) || 0
        let downloadedBytes = 0
        const startedAt = Date.now()
        let lastEmitAt = 0

        out = fs.createWriteStream(tmpPath)
        out.on('error', finishReject)
        res.on('error', finishReject)

        res.on('data', chunk => {
          downloadedBytes += chunk.length
          const now = Date.now()
          if (onProgress && now - lastEmitAt >= 200) {
            lastEmitAt = now
            const elapsedSec = Math.max(0.1, (now - startedAt) / 1000)
            onProgress({
              downloadedBytes,
              totalBytes,
              percent: totalBytes > 0 ? Math.min(99, Math.round((downloadedBytes / totalBytes) * 100)) : null,
              speedBps: Math.round(downloadedBytes / elapsedSec)
            })
          }
        })

        res.pipe(out)
        out.on('finish', async () => {
          if (abortSignal) abortSignal.removeEventListener('abort', onAbort)
          if (settled) return
          try {
            await new Promise(r => out.close(r))
            await fsp.rename(tmpPath, destPath)
            settled = true
            if (onProgress) {
              onProgress({
                downloadedBytes,
                totalBytes: totalBytes || downloadedBytes,
                percent: 100,
                speedBps: 0
              })
            }
            resolve(destPath)
          } catch (err) {
            finishReject(err)
          }
        })
      }
    )

    req.setTimeout(30_000, () => {
      req.destroy(new Error(`Download stalled for ${url}`))
    })
    req.on('error', finishReject)
  })
}

async function extractRuntimeArchive(archivePath, destDir, archiveType, platform = process.platform) {
  await fsp.mkdir(destDir, { recursive: true })
  await new Promise((resolve, reject) => {
    if (archiveType === 'zip' && platform === 'win32') {
      execFile(
        'powershell.exe',
        [
          '-NoProfile',
          '-NonInteractive',
          '-Command',
          `Expand-Archive -LiteralPath '${archivePath.replace(/'/g, "''")}' -DestinationPath '${destDir.replace(/'/g, "''")}' -Force`
        ],
        { windowsHide: true, timeout: 120_000 },
        (err, _stdout, stderr) => {
          if (err) reject(new Error(stderr || err.message))
          else resolve()
        }
      )
      return
    }

    const cmd = archiveType === 'zip' ? 'unzip' : 'tar'
    const args = archiveType === 'zip' ? ['-o', archivePath, '-d', destDir] : ['-xzf', archivePath, '-C', destDir]
    execFile(cmd, args, { timeout: 120_000 }, (err, _stdout, stderr) => {
      if (err) reject(new Error(stderr || err.message))
      else resolve()
    })
  })
}

function findBinaryRecursive(dir, binaryName, depth = 0) {
  if (!dir || depth > 2) return null
  let entries
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return null
  }
  for (const entry of entries) {
    if (entry.isFile() && entry.name.toLowerCase() === binaryName.toLowerCase()) {
      return path.join(dir, entry.name)
    }
  }
  for (const entry of entries) {
    if (entry.isDirectory()) {
      const nested = findBinaryRecursive(path.join(dir, entry.name), binaryName, depth + 1)
      if (nested) return nested
    }
  }
  return null
}

function createBusinessLocalAiManager(options = {}) {
  const hermesHome = path.resolve(String(options.hermesHome || path.join(os.homedir(), '.hermes')))
  const baseDir = path.join(hermesHome, 'business-agent')
  const runtimeDir = path.join(baseDir, 'runtime')
  const modelsDir = path.join(baseDir, 'models')
  const configPath = path.join(baseDir, 'config.json')
  const ocrHelperSourcePath = options.ocrHelperSourcePath || path.join(__dirname, 'business-ocr-helper.py')
  const ocrHelperCachedPath = path.join(baseDir, 'ocr-helper.py')
  const platform = options.platform || process.platform
  const arch = options.arch || process.arch
  const log = typeof options.log === 'function' ? options.log : () => {}
  const onStatus = typeof options.onStatus === 'function' ? options.onStatus : () => {}
  const findPython = typeof options.findPython === 'function' ? options.findPython : () => null
  const fetchJsonImpl = options.fetchJson || requestJson
  const downloadFileImpl = options.downloadFile || downloadFileWithProgress
  const extractArchiveImpl = options.extractArchive || extractRuntimeArchive
  const minValidModelBytes = Number.isFinite(options.minValidModelBytes)
    ? options.minValidModelBytes
    : MIN_VALID_MODEL_BYTES

  const hardware = detectHardwareProfile({
    totalMemoryBytes: options.totalMemoryBytes,
    freeMemoryBytes: options.freeMemoryBytes,
    cpuCount: options.cpuCount
  })

  let config = readStoredConfig()
  let childProc = null
  let serverPort = null
  let serverModelId = null
  let startedAt = null
  let lastUsedAt = 0
  let startPromise = null
  let idleTimer = null
  let installAbortController = null
  let installProgress = null
  let inferenceTail = Promise.resolve()
  let cachedMemory = { pid: null, at: 0, mb: null }
  let lastError = null

  function defaultConfig() {
    return {
      enabled: true,
      modelId: hardware.recommendedModelId,
      idleUnloadMs: DEFAULT_IDLE_UNLOAD_MS,
      ctxSize: hardware.isLowRamPc ? 1024 : 1024,
      threads: 0,
      useKvQuant: true
    }
  }

  function readStoredConfig() {
    const defaults = defaultConfig()
    try {
      const raw = fs.readFileSync(configPath, 'utf8')
      const parsed = JSON.parse(raw)
      if (!parsed || typeof parsed !== 'object') return defaults
      return {
        ...defaults,
        enabled: typeof parsed.enabled === 'boolean' ? parsed.enabled : defaults.enabled,
        modelId: MODEL_BY_ID.has(parsed.modelId) ? parsed.modelId : defaults.modelId,
        idleUnloadMs:
          Number.isFinite(parsed.idleUnloadMs) && parsed.idleUnloadMs >= 0
            ? Math.round(parsed.idleUnloadMs)
            : defaults.idleUnloadMs,
        ctxSize: clampCtxSize(parsed.ctxSize, defaults.ctxSize),
        threads: Number.isFinite(parsed.threads) && parsed.threads >= 0 ? Math.round(parsed.threads) : 0,
        useKvQuant: typeof parsed.useKvQuant === 'boolean' ? parsed.useKvQuant : defaults.useKvQuant
      }
    } catch {
      return defaults
    }
  }

  function saveStoredConfig(next) {
    config = next
    try {
      fs.mkdirSync(baseDir, { recursive: true })
      fs.writeFileSync(configPath, JSON.stringify(next, null, 2) + '\n', 'utf8')
    } catch (err) {
      log(`[business-ai] failed to persist config: ${err.message}`)
    }
  }

  function resolveLlamaServerBinary() {
    const override = process.env.HERMES_BUSINESS_LLAMA_SERVER
    if (override && fs.existsSync(override)) return override
    const matcher = getPlatformRuntimeAssetMatcher(platform, arch)
    const binaryName = matcher ? matcher.binaryName : platform === 'win32' ? 'llama-server.exe' : 'llama-server'
    return findBinaryRecursive(runtimeDir, binaryName)
  }

  function getModelPath(modelId) {
    const spec = getModelSpec(modelId)
    return path.join(modelsDir, spec.filename)
  }

  function isModelInstalled(modelId) {
    const filePath = getModelPath(modelId)
    try {
      const stat = fs.statSync(filePath)
      return stat.isFile() && stat.size >= minValidModelBytes
    } catch {
      return false
    }
  }

  function listInstalledModelIds() {
    return BUSINESS_LOCAL_MODELS.filter(m => isModelInstalled(m.id)).map(m => m.id)
  }

  function clearIdleTimer() {
    if (idleTimer) {
      clearTimeout(idleTimer)
      idleTimer = null
