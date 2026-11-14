import type { BusinessDocument } from '../types'

import { serializeBusinessDocument } from './document-serializer'

const PAGE_WIDTH = 595.28
const PAGE_HEIGHT = 841.89
const MARGIN_X = 48
const TOP_Y = 785
const BOTTOM_Y = 62
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN_X * 2

const WIN_ANSI_MAP: Record<number, number> = {
  338: 140,
  339: 156,
  352: 138,
  353: 154,
  376: 159,
  381: 142,
  382: 158,
  402: 131,
  710: 136,
  732: 152,
  8211: 150,
  8212: 151,
  8216: 145,
  8217: 146,
  8218: 130,
  8220: 147,
  8221: 148,
  8222: 132,
  8224: 134,
  8225: 135,
  8226: 149,
  8230: 133,
  8240: 137,
  8249: 139,
  8250: 155,
  8364: 128,
  8482: 153
}

function encodePdfText(text: string): string {
  const normalized = (text || '').replace(/→/g, '->').replace(/✓/g, '[OK]').replace(/·/g, '-')
  let out = ''

  for (let i = 0; i < normalized.length; i++) {
    const code = normalized.charCodeAt(i)
    let byte = 63

    if ((code >= 32 && code <= 126) || (code >= 160 && code <= 255)) {
      byte = code
    } else if (WIN_ANSI_MAP[code] !== undefined) {
      byte = WIN_ANSI_MAP[code] ?? 63
    }

    if (byte === 40 || byte === 41 || byte === 92) {
      out += `\\${String.fromCharCode(byte)}`
    } else if (byte < 32 || byte > 126) {
      out += `\\${byte.toString(8).padStart(3, '0')}`
    } else {
      out += String.fromCharCode(byte)
    }
  }

  return out
}

function parseHexRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '').trim()

  if (clean.length !== 6) {
    return [0, 0.32, 0.99]
  }

  const r = parseInt(clean.slice(0, 2), 16) / 255
  const g = parseInt(clean.slice(2, 4), 16) / 255
  const b = parseInt(clean.slice(4, 6), 16) / 255

  return [
    Number.isFinite(r) ? Number(r.toFixed(3)) : 0,
    Number.isFinite(g) ? Number(g.toFixed(3)) : 0.32,
    Number.isFinite(b) ? Number(b.toFixed(3)) : 0.99
  ]
}

function wrapText(text: string, maxChars: number): string[] {
  const rawLines = (text || '').split(/\r?\n/)
  const lines: string[] = []

  for (const raw of rawLines) {
    const words = raw.trim().split(/\s+/).filter(Boolean)

    if (words.length === 0) {
      lines.push('')

      continue
    }

    let current = ''

    for (const word of words) {
      const candidate = current ? `${current} ${word}` : word

      if (candidate.length <= maxChars) {
        current = candidate
      } else {
        if (current) {
          lines.push(current)
        }

        if (word.length > maxChars) {
          for (let i = 0; i < word.length; i += maxChars) {
            lines.push(word.slice(i, i + maxChars))
          }

          current = ''
        } else {
          current = word
        }
      }
    }

    if (current) {
      lines.push(current)
    }
  }

  return lines
}

/**
 * Generate a multi-page PDF 1.4 binary with Helvetica/Helvetica-Bold WinAnsi typography.
 */
export function buildPdfBytes(doc: BusinessDocument): Uint8Array {
  const blocks = serializeBusinessDocument(doc)
  const pages: string[][] = [[]]
  let cursorY = TOP_Y

  const activePage = (): string[] => {
    const current = pages[pages.length - 1]

    if (!current) {
      const created: string[] = []

      pages.push(created)

      return created
    }

    return current
  }

  const ensureSpace = (height: number): void => {
    if (cursorY - height < BOTTOM_Y) {
      pages.push([])
      cursorY = TOP_Y
    }
  }

  const drawText = (
    text: string,
    x: number,
    y: number,
    font: 'F1' | 'F2',
    size: number,
    rgb: [number, number, number] = [0.08, 0.1, 0.14]
  ): void => {
    activePage().push(
      `BT /${font} ${size} Tf ${rgb[0]} ${rgb[1]} ${rgb[2]} rg ${x.toFixed(2)} ${y.toFixed(2)} Td (${encodePdfText(text)}) Tj ET`
    )
  }

  for (const block of blocks) {
    if (block.type === 'header') {
      ensureSpace(74)
      const [r, g, b] = parseHexRgb(block.accentColor)
      const boxY = cursorY - 58 + 12

      activePage().push(`${r} ${g} ${b} rg ${MARGIN_X} ${boxY.toFixed(2)} ${CONTENT_WIDTH.toFixed(2)} 58 re f`)
      drawText(block.title, MARGIN_X + 14, boxY + 34, 'F2', 16, [1, 1, 1])

      wrapText(block.subtitle, 86)
        .slice(0, 2)
        .forEach((line, idx) => {
          drawText(line, MARGIN_X + 14, boxY + 18 - idx * 11, 'F1', 8.5, [0.92, 0.95, 1])
        })

      cursorY = boxY - 16
    } else if (block.type === 'heading') {
      const isMain = block.level === 1

      ensureSpace(isMain ? 30 : 22)
      cursorY -= isMain ? 8 : 4
      drawText(block.text, MARGIN_X, cursorY, 'F2', isMain ? 11.5 : 10, isMain ? [0.05, 0.2, 0.55] : [0.15, 0.18, 0.24])

      if (isMain) {
        activePage().push(
          `0.82 0.85 0.90 RG 0.7 w ${MARGIN_X} ${(cursorY - 4).toFixed(2)} m ${(MARGIN_X + CONTENT_WIDTH).toFixed(2)} ${(cursorY - 4).toFixed(2)} l S`
        )
        cursorY -= 16
      } else {
        cursorY -= 13
      }
    } else if (block.type === 'paragraph') {
      const lines = wrapText(block.text, 88)

      for (const line of lines) {
        ensureSpace(14)
        drawText(line, MARGIN_X, cursorY, 'F1', 9.5, [0.14, 0.16, 0.2])
        cursorY -= 13
      }

      cursorY -= 4
    } else if (block.type === 'bullets') {
      for (const item of block.items) {
        wrapText(item, 82).forEach((line, idx) => {
          ensureSpace(14)
          drawText(`${idx === 0 ? '• ' : '  '}${line}`, MARGIN_X + 8, cursorY, 'F1', 9.5, [0.14, 0.16, 0.2])
          cursorY -= 13
        })
      }

      cursorY -= 4
    } else if (block.type === 'keyValueGrid') {
      for (const pair of block.pairs) {
        wrapText(`${pair.label}: ${pair.value}`, 86).forEach((line, idx) => {
          ensureSpace(14)
          drawText(line, MARGIN_X + 4, cursorY, idx === 0 ? 'F2' : 'F1', 9, [0.18, 0.2, 0.26])
          cursorY -= 12.5
        })
      }

      cursorY -= 6
    } else if (block.type === 'callout') {
      const lines = wrapText(block.text, 82)
      const boxHeight = lines.length * 12 + 12

      ensureSpace(boxHeight + 8)
      const boxY = cursorY - boxHeight + 8
      const bg: [number, number, number] = block.kind === 'warning' ? [1, 0.96, 0.88] : [0.93, 0.96, 1]

      activePage().push(`${bg[0]} ${bg[1]} ${bg[2]} rg ${MARGIN_X} ${boxY.toFixed(2)} ${CONTENT_WIDTH.toFixed(2)} ${boxHeight} re f`)
      lines.forEach((line, idx) => {
        drawText(
          line,
          MARGIN_X + 10,
          cursorY - 4 - idx * 12,
          'F2',
          8.5,
          block.kind === 'warning' ? [0.55, 0.32, 0.04] : [0.05, 0.24, 0.55]
        )
      })
      cursorY = boxY - 12
    } else if (block.type === 'table') {
      const colCount = Math.max(1, block.headers.length)
      const colWidth = CONTENT_WIDTH / colCount
      const maxColChars = Math.max(8, Math.floor(84 / colCount))

      ensureSpace(24)
      const headerBoxY = cursorY - 14

      activePage().push(`0.92 0.94 0.97 rg ${MARGIN_X} ${headerBoxY.toFixed(2)} ${CONTENT_WIDTH.toFixed(2)} 18 re f`)
      block.headers.forEach((header, colIdx) => {
        drawText(header.slice(0, maxColChars), MARGIN_X + colIdx * colWidth + 4, cursorY - 9, 'F2', 8.5, [0.1, 0.14, 0.22])
      })
      cursorY -= 18

      for (const row of block.rows) {
        const wrappedCells = row.map(cell => wrapText(cell, maxColChars))
        const rowHeight = Math.max(1, ...wrappedCells.map(lines => lines.length)) * 11 + 6

        ensureSpace(rowHeight + 4)
        const rowBoxY = cursorY - rowHeight + 4

        activePage().push(
          `0.86 0.88 0.92 RG 0.5 w ${MARGIN_X} ${rowBoxY.toFixed(2)} ${CONTENT_WIDTH.toFixed(2)} ${rowHeight.toFixed(2)} re S`
        )
        wrappedCells.forEach((cellLines, colIdx) => {
          cellLines.forEach((line, lineIdx) => {
            drawText(line, MARGIN_X + colIdx * colWidth + 4, cursorY - 8 - lineIdx * 11, 'F1', 8.5, [0.15, 0.17, 0.22])
          })
        })
        cursorY -= rowHeight
      }

      cursorY -= 10
    } else if (block.type === 'signatures') {
      ensureSpace(56)
      cursorY -= 12
      drawText(block.leftLabel, MARGIN_X, cursorY, 'F2', 9.5, [0.15, 0.18, 0.24])
      drawText(block.leftName, MARGIN_X, cursorY - 14, 'F1', 9, [0.25, 0.28, 0.34])

      if (block.rightLabel) {
        const rightX = MARGIN_X + CONTENT_WIDTH / 2 + 16

        drawText(block.rightLabel, rightX, cursorY, 'F2', 9.5, [0.15, 0.18, 0.24])

        if (block.rightName) {
          drawText(block.rightName, rightX, cursorY - 14, 'F1', 9, [0.25, 0.28, 0.34])
        }
      }

      cursorY -= 42
    }
  }

  const totalPages = pages.length

  pages.forEach((commands, pageIdx) => {
    const footer = `${doc.title} — Page ${pageIdx + 1} / ${totalPages}`

    commands.push(`BT /F1 8 Tf 0.45 0.48 0.54 rg ${MARGIN_X} 32 Td (${encodePdfText(footer)}) Tj ET`)
  })

  const objects: string[] = []
  const pageObjectIds: number[] = []

  objects.push('1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj')
  objects.push('')
  objects.push('3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj')
  objects.push('4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj')

  pages.forEach((commands, idx) => {
    const pageObjId = 5 + idx * 2
    const streamObjId = 6 + idx * 2

    pageObjectIds.push(pageObjId)
    const contentStream = commands.join('\n')

    objects.push(
      `${pageObjId} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_WIDTH} ${PAGE_HEIGHT}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${streamObjId} 0 R >>\nendobj`
    )
    objects.push(`${streamObjId} 0 obj\n<< /Length ${contentStream.length} >>\nstream\n${contentStream}\nendstream\nendobj`)
  })

  objects[1] = `2 0 obj\n<< /Type /Pages /Kids [${pageObjectIds.map(id => `${id} 0 R`).join(' ')}] /Count ${pageObjectIds.length} >>\nendobj`

  let pdfString = '%PDF-1.4\n%âãÏÓ\n'
  const offsets: number[] = [0]

  for (const obj of objects) {
    offsets.push(pdfString.length)
    pdfString += `${obj}\n`
  }

  const xrefOffset = pdfString.length

  pdfString += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`

  for (let i = 1; i <= objects.length; i++) {
    const offset = offsets[i] ?? 0

    pdfString += `${String(offset).padStart(10, '0')} 00000 n \n`
  }

  pdfString += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`

  const bytes = new Uint8Array(pdfString.length)

  for (let i = 0; i < pdfString.length; i++) {
    bytes[i] = pdfString.charCodeAt(i) & 0xff
  }

  return bytes
}
