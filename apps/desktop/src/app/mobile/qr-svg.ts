// Spec-compliant ISO 18004 Byte-mode QR matrix generator (Versions 1..6, ECC-L).
// Supports UTF-8 strings up to 134 bytes (sufficient for full download URLs).

const EXP = new Uint8Array(512)
const LOG = new Uint8Array(256)

let gfVal = 1
for (let i = 0; i < 255; i++) {
  EXP[i] = gfVal
  LOG[gfVal] = i
  gfVal <<= 1
  if (gfVal & 0x100) {
    gfVal ^= 0x11d
  }
}
for (let i = 255; i < 512; i++) {
  EXP[i] = EXP[i - 255]
}

function gfMul(a: number, b: number): number {
  if (a === 0 || b === 0) return 0
  return EXP[LOG[a] + LOG[b]]
}

function rsGeneratorPoly(degree: number): number[] {
  let poly = [1]
  for (let i = 0; i < degree; i++) {
    const next = new Array<number>(poly.length + 1).fill(0)
    const factor = EXP[i]
    for (let j = 0; j < poly.length; j++) {
      next[j] ^= poly[j]
      next[j + 1] ^= gfMul(poly[j], factor)
    }
    poly = next
  }
  return poly
}

function rsRemainder(data: number[], eccCount: number): number[] {
  const gen = rsGeneratorPoly(eccCount)
  const buf = new Array<number>(data.length + eccCount).fill(0)
  for (let i = 0; i < data.length; i++) buf[i] = data[i]
  for (let i = 0; i < data.length; i++) {
    const coef = buf[i]
    if (coef !== 0) {
      for (let j = 0; j < gen.length; j++) {
        buf[i + j] ^= gfMul(gen[j], coef)
      }
    }
  }
  return buf.slice(data.length)
}

interface VersionSpec {
  version: number
  size: number
  totalDataBytes: number
  eccPerBlock: number
  blocks: number
  alignCenters: number[]
}

// ISO 18004 Error Correction Level L tables for versions 1..6
const VERSIONS_ECC_L: readonly VersionSpec[] = [
  { version: 1, size: 21, totalDataBytes: 19, eccPerBlock: 7, blocks: 1, alignCenters: [] },
  { version: 2, size: 25, totalDataBytes: 34, eccPerBlock: 10, blocks: 1, alignCenters: [6, 18] },
  { version: 3, size: 29, totalDataBytes: 55, eccPerBlock: 15, blocks: 1, alignCenters: [6, 22] },
  { version: 4, size: 33, totalDataBytes: 80, eccPerBlock: 20, blocks: 1, alignCenters: [6, 26] },
  { version: 5, size: 37, totalDataBytes: 108, eccPerBlock: 26, blocks: 1, alignCenters: [6, 30] },
  { version: 6, size: 41, totalDataBytes: 136, eccPerBlock: 18, blocks: 2, alignCenters: [6, 34] }
]

// Mask format strings (ECC Level L = 01, masks 0..7) precomputed with BCH + XOR 0x5412
const FORMAT_BITS_L = [0x77c4, 0x72f3, 0x7daa, 0x789d, 0x662f, 0x6318, 0x6c41, 0x6976] as const

export interface QrMatrix {
  size: number
  modules: boolean[][]
}

export function generateQrMatrix(text: string): QrMatrix {
  const bytes = Array.from(new TextEncoder().encode(text))
  const spec =
    VERSIONS_ECC_L.find(v => v.totalDataBytes >= 2 + bytes.length) ?? VERSIONS_ECC_L[VERSIONS_ECC_L.length - 1]
  const payload = bytes.slice(0, spec.totalDataBytes - 2)

  // Bit buffer: Mode 0100 (4 bits) + char count (8 bits for v1..9) + data + terminator
  const bits: number[] = []
  const pushBits = (val: number, len: number) => {
    for (let i = len - 1; i >= 0; i--) bits.push((val >>> i) & 1)
  }

  pushBits(0b0100, 4)
  pushBits(payload.length, 8)
  for (const b of payload) pushBits(b, 8)
  const capBits = spec.totalDataBytes * 8
  pushBits(0, Math.min(4, capBits - bits.length))
  while (bits.length % 8 !== 0) bits.push(0)

  const dataBytes: number[] = []
  for (let i = 0; i < bits.length; i += 8) {
    let byte = 0
    for (let j = 0; j < 8; j++) byte = (byte << 1) | bits[i + j]
    dataBytes.push(byte)
  }

  const pads = [0xec, 0x11]
  let padIdx = 0
  while (dataBytes.length < spec.totalDataBytes) {
    dataBytes.push(pads[padIdx++ % 2])
  }

  // Split into RS blocks and interleave
  const blockSize = Math.floor(spec.totalDataBytes / spec.blocks)
  const dataBlocks: number[][] = []
  const eccBlocks: number[][] = []
  let offset = 0
  for (let b = 0; b < spec.blocks; b++) {
    const blk = dataBytes.slice(offset, offset + blockSize)
    offset += blockSize
    dataBlocks.push(blk)
    eccBlocks.push(rsRemainder(blk, spec.eccPerBlock))
  }

  const interleaved: number[] = []
  for (let i = 0; i < blockSize; i++) {
    for (let b = 0; b < spec.blocks; b++) interleaved.push(dataBlocks[b][i])
  }
  for (let i = 0; i < spec.eccPerBlock; i++) {
    for (let b = 0; b < spec.blocks; b++) interleaved.push(eccBlocks[b][i])
  }

  const n = spec.size
  const modules: boolean[][] = Array.from({ length: n }, () => new Array<boolean>(n).fill(false))
  const reserved: boolean[][] = Array.from({ length: n }, () => new Array<boolean>(n).fill(false))

  const setModule = (r: number, c: number, dark: boolean, lock = true) => {
    if (r < 0 || c < 0 || r >= n || c >= n) return
    modules[r][c] = dark
    if (lock) reserved[r][c] = true
  }

  const drawFinder = (top: number, left: number) => {
    for (let dr = -1; dr <= 7; dr++) {
      for (let dc = -1; dc <= 7; dc++) {
        const r = top + dr
        const c = left + dc
        if (r < 0 || c < 0 || r >= n || c >= n) continue
        const inBox = dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6
        const dark =
          inBox &&
          (dr === 0 || dr === 6 || dc === 0 || dc === 6 || (dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4))
        setModule(r, c, dark)
      }
    }
  }

  drawFinder(0, 0)
  drawFinder(0, n - 7)
  drawFinder(n - 7, 0)

  // Alignment patterns
  const centers = spec.alignCenters
  for (const cr of centers) {
    for (const cc of centers) {
      const overlapsFinder =
        (cr <= 8 && cc <= 8) || (cr <= 8 && cc >= n - 9) || (cr >= n - 9 && cc <= 8)
      if (overlapsFinder) continue
      for (let dr = -2; dr <= 2; dr++) {
        for (let dc = -2; dc <= 2; dc++) {
          const dark = Math.max(Math.abs(dr), Math.abs(dc)) !== 1
          setModule(cr + dr, cc + dc, dark)
        }
      }
    }
  }

  // Timing patterns
  for (let i = 8; i < n - 8; i++) {
    setModule(6, i, i % 2 === 0)
    setModule(i, 6, i % 2 === 0)
  }

  // Dark module + format reservation
  setModule(4 * spec.version + 9, 8, true)
  for (let i = 0; i < 9; i++) {
    if (!reserved[8][i]) reserved[8][i] = true
    if (!reserved[i][8]) reserved[i][8] = true
  }
  for (let i = 0; i < 8; i++) {
    reserved[8][n - 1 - i] = true
    if (i < 7) reserved[n - 1 - i][8] = true
  }

  // Place data bits in zigzag
  const bitStream: number[] = []
  for (const byte of interleaved) {
    for (let i = 7; i >= 0; i--) bitStream.push((byte >>> i) & 1)
  }

  let bitIdx = 0
  let up = true
  for (let col = n - 1; col >= 1; col -= 2) {
    if (col === 6) col--
    for (let step = 0; step < n; step++) {
      const r = up ? n - 1 - step : step
      for (let dc = 0; dc < 2; dc++) {
        const c = col - dc
        if (!reserved[r][c]) {
          const bit = bitIdx < bitStream.length ? bitStream[bitIdx++] === 1 : false
          modules[r][c] = bit
        }
      }
    }
    up = !up
  }

  // Evaluate mask patterns 0..7 and pick lowest penalty
  const maskFns = [
    (r: number, c: number) => (r + c) % 2 === 0,
    (r: number) => r % 2 === 0,
    (_r: number, c: number) => c % 3 === 0,
    (r: number, c: number) => (r + c) % 3 === 0,
    (r: number, c: number) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
    (r: number, c: number) => ((r * c) % 2) + ((r * c) % 3) === 0,
    (r: number, c: number) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
    (r: number, c: number) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0
  ]

  const applyFormat = (grid: boolean[][], mask: number) => {
    const fmt = FORMAT_BITS_L[mask]
    for (let i = 0; i < 15; i++) {
      const bit = ((fmt >>> i) & 1) === 1
      if (i < 6) grid[i][8] = bit
      else if (i < 8) grid[i + 1][8] = bit
      else grid[n - 15 + i][8] = bit

      if (i < 8) grid[8][n - 1 - i] = bit
      else if (i < 9) grid[8][7] = bit
      else grid[8][14 - i] = bit
    }
  }

  const penalty = (grid: boolean[][]): number => {
    let score = 0
    for (let r = 0; r < n; r++) {
      let run = 1
      for (let c = 1; c < n; c++) {
        if (grid[r][c] === grid[r][c - 1]) {
          run++
          if (run === 5) score += 3
          else if (run > 5) score += 1
        } else run = 1
      }
    }
    for (let c = 0; c < n; c++) {
      let run = 1
      for (let r = 1; r < n; r++) {
        if (grid[r][c] === grid[r - 1][c]) {
          run++
          if (run === 5) score += 3
          else if (run > 5) score += 1
        } else run = 1
      }
    }
    for (let r = 0; r < n - 1; r++) {
      for (let c = 0; c < n - 1; c++) {
        const b = grid[r][c]
        if (b === grid[r][c + 1] && b === grid[r + 1][c] && b === grid[r + 1][c + 1]) score += 3
      }
    }
    return score
  }

  let bestMask = 0
  let bestScore = Infinity
  let bestGrid = modules

  for (let m = 0; m < 8; m++) {
    const trial = modules.map((row, r) => row.map((v, c) => (!reserved[r][c] && maskFns[m](r, c) ? !v : v)))
    applyFormat(trial, m)
    const p = penalty(trial)
    if (p < bestScore) {
      bestScore = p
      bestMask = m
      bestGrid = trial
    }
  }

  void bestMask
  return { size: n, modules: bestGrid }
}
