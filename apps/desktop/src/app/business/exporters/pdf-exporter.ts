import type { BusinessDocument } from '../types'

import { serializeBusinessDocument, type SerializedBlock } from './document-serializer'

const A4_WIDTH = 595.28
const A4_HEIGHT = 841.89
const MARGIN_X = 48
const TOP_START_Y = 785
const BOTTOM_LIMIT_Y = 62
const CONTENT_WIDTH = A4_WIDTH - MARGIN_X * 2

const WIN_ANSI_EXTRAS: Record<number, number> = {
  0x20ac: 128, // €
  0x201a: 130,
  0x0192: 131,
  0x201e: 132,
  0x2026: 133, // …
  0x2020: 134,
  0x2021: 135,
  0x02c6: 136,
  0x2030: 137,
  0x0160: 138,
  0x2039: 139,
  0x0152: 140, // Œ
  0x017d: 142,
  0x2018: 145, // ‘
  0x2019: 146, // ’
  0x201c: 147, // “
  0x201d: 148, // ”
  0x2022: 149, // •
  0x2013: 150, // –
  0x2014: 151, // —
  0x02dc: 152,
  0x2122: 153,
  0x0161: 154,
  0x203a: 155,
  0x0153: 156, // œ
  0x017e: 158,
  0x0178: 159
}

function encodePdfText(input: string): string {
  const normalized = (input || '')
    .replace(/→/g, '->')
    .replace(/✓/g, '[OK]')
    .replace(/·/g, '-')

  let out = ''

  for (let i = 0; i < normalized.length; i++) {
    const code = normalized.charCodeAt(i)
    let byte = 63 // '?'

    if (code >= 32 && code <= 126) {
      byte = code
    } else if (code >= 160 && code <= 255) {
      byte = code
    } else if (WIN_ANSI_EXTRAS[code] !== undefined) {
      byte = WIN_ANSI_EXTRAS[code] ?? 63
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

function hexToRgbFloats(hex: string): [number, number, number] {
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

function wrapTextToLines(text: string, maxCharsPerLine: number): string[] {
  const paragraphs = (text || '').split(/\r?\n/)
  const lines: string[] = []

  for (const para of paragraphs) {
    const words = para.trim().split(/\s+/).filter(Boolean)

    if (words.length === 0) {
      lines.push('')

      continue
    }

    let current = ''

    for (const word of words) {
      const candidate = current ? `${current} ${word}` : word

      if (candidate.length <= maxCharsPerLine) {
        current = candidate
      } else {
        if (current) {
          lines.push(current)
        }

        if (word.length > maxCharsPerLine) {
          for (let pos = 0; pos < word.length; pos += maxCharsPerLine) {
            lines.push(word.slice(pos, pos + maxCharsPerLine))
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
 * Generates a real, multi-page A4 PDF 1.4 binary document (%PDF-1.4) with WinAnsi
 * Latin-1 / French accent support, colored header banners, tables, and page numbers.
 */
export function generatePdfBytes(doc: BusinessDocument): Uint8Array {
  const blocks: SerializedBlock[] = serializeBusinessDocument(doc)
  const pages: string[][] = [[]]
  let currentY = TOP_START_Y

  const activePage = (): string[] => {
    const last = pages[pages.length - 1]

    if (!last) {
      const created: string[] = []
      pages.push(created)

      return created
    }

    return last
  }

  const ensureVerticalSpace = (requiredPts: number) => {
    if (currentY - requiredPts < BOTTOM_LIMIT_Y) {
      pages.push([])
      currentY = TOP_START_Y
    }
  }

  const drawTextLine = (
    text: string,
    x: number,
    y: number,
    font: 'F1' | 'F2',
    size: number,
    rgb: [number, number, number] = [0.08, 0.1, 0.14]
  ) => {
    activePage().push(
      `BT /${font} ${size} Tf ${rgb[0]} ${rgb[1]} ${rgb[2]} rg ${x.toFixed(2)} ${y.toFixed(2)} Td (${encodePdfText(text)}) Tj ET`
    )
  }

  for (const block of blocks) {
    if (block.type === 'header') {
      ensureVerticalSpace(74)
      const [r, g, b] = hexToRgbFloats(block.accentColor)
      const boxHeight = 58
      const boxBottom = currentY - boxHeight + 12
      activePage().push(
        `${r} ${g} ${b} rg ${MARGIN_X} ${boxBottom.toFixed(2)} ${CONTENT_WIDTH.toFixed(2)} ${boxHeight} re f`
      )
      drawTextLine(block.title, MARGIN_X + 14, boxBottom + 34, 'F2', 16, [1, 1, 1])

      const subLines = wrapTextToLines(block.subtitle, 86).slice(0, 2)
      subLines.forEach((line, idx) => {
        drawTextLine(line, MARGIN_X + 14, boxBottom + 18 - idx * 11, 'F1', 8.5, [0.92, 0.95, 1])
      })
      currentY = boxBottom - 16
    } else if (block.type === 'heading') {
      const isH1 = block.level === 1
      ensureVerticalSpace(isH1 ? 30 : 22)
      currentY -= isH1 ? 8 : 4
      drawTextLine(
        block.text,
        MARGIN_X,
        currentY,
        'F2',
        isH1 ? 11.5 : 10,
        isH1 ? [0.05, 0.2, 0.55] : [0.15, 0.18, 0.24]
      )

      if (isH1) {
        activePage().push(
          `0.82 0.85 0.90 RG 0.7 w ${MARGIN_X} ${(currentY - 4).toFixed(2)} m ${(MARGIN_X + CONTENT_WIDTH).toFixed(2)} ${(currentY - 4).toFixed(2)} l S`
        )
        currentY -= 16
      } else {
        currentY -= 13
      }
    } else if (block.type === 'paragraph') {
      const lines = wrapTextToLines(block.text, 88)

      for (const line of lines) {
        ensureVerticalSpace(14)
        drawTextLine(line, MARGIN_X, currentY, 'F1', 9.5, [0.14, 0.16, 0.2])
        currentY -= 13
      }

      currentY -= 4
    } else if (block.type === 'bullets') {
      for (const item of block.items) {
        const lines = wrapTextToLines(item, 82)
        lines.forEach((line, idx) => {
          ensureVerticalSpace(14)
          const prefix = idx === 0 ? '• ' : '  '
          drawTextLine(`${prefix}${line}`, MARGIN_X + 8, currentY, 'F1', 9.5, [0.14, 0.16, 0.2])
          currentY -= 13
        })
      }

      currentY -= 4
    } else if (block.type === 'keyValueGrid') {
      for (const pair of block.pairs) {
        const lines = wrapTextToLines(`${pair.label}: ${pair.value}`, 86)
        lines.forEach((line, idx) => {
          ensureVerticalSpace(14)
          drawTextLine(
            line,
            MARGIN_X + 4,
            currentY,
            idx === 0 ? 'F2' : 'F1',
            9,
            [0.18, 0.2, 0.26]
          )
          currentY -= 12.5
        })
      }

      currentY -= 6
    } else if (block.type === 'callout') {
      const lines = wrapTextToLines(block.text, 82)
      const boxH = lines.length * 12 + 12
      ensureVerticalSpace(boxH + 8)
      const boxBottom = currentY - boxH + 8

      const bg: [number, number, number] =
        block.kind === 'warning' ? [1, 0.96, 0.88] : [0.93, 0.96, 1]

      activePage().push(
        `${bg[0]} ${bg[1]} ${bg[2]} rg ${MARGIN_X} ${boxBottom.toFixed(2)} ${CONTENT_WIDTH.toFixed(2)} ${boxH} re f`
      )
      lines.forEach((line, idx) => {
        drawTextLine(
          line,
          MARGIN_X + 10,
          currentY - 4 - idx * 12,
          'F2',
          8.5,
          block.kind === 'warning' ? [0.55, 0.32, 0.04] : [0.05, 0.24, 0.55]
        )
      })
      currentY = boxBottom - 12
    } else if (block.type === 'table') {
      const colCount = Math.max(1, block.headers.length)
      const colWidth = CONTENT_WIDTH / colCount
      const maxCharsPerCell = Math.max(8, Math.floor(84 / colCount))

      ensureVerticalSpace(24)
      const headerBottom = currentY - 14
      activePage().push(
        `0.92 0.94 0.97 rg ${MARGIN_X} ${headerBottom.toFixed(2)} ${CONTENT_WIDTH.toFixed(2)} 18 re f`
      )
      block.headers.forEach((h, cIdx) => {
        drawTextLine(
          h.slice(0, maxCharsPerCell),
          MARGIN_X + cIdx * colWidth + 4,
          currentY - 9,
          'F2',
          8.5,
          [0.1, 0.14, 0.22]
        )
      })
      currentY -= 18

      for (const row of block.rows) {
        const wrappedCells = row.map(cell => wrapTextToLines(cell, maxCharsPerCell))
        const maxLines = Math.max(1, ...wrappedCells.map(lines => lines.length))
        const rowHeight = maxLines * 11 + 6

        ensureVerticalSpace(rowHeight + 4)
        const rowBottom = currentY - rowHeight + 4

        activePage().push(
          `0.86 0.88 0.92 RG 0.5 w ${MARGIN_X} ${rowBottom.toFixed(2)} ${CONTENT_WIDTH.toFixed(2)} ${rowHeight.toFixed(2)} re S`
        )

        wrappedCells.forEach((cellLines, cIdx) => {
          cellLines.forEach((line, lIdx) => {
            drawTextLine(
              line,
              MARGIN_X + cIdx * colWidth + 4,
              currentY - 8 - lIdx * 11,
              'F1',
              8.5,
              [0.15, 0.17, 0.22]
            )
          })
        })

        currentY -= rowHeight
      }

      currentY -= 10
    } else if (block.type === 'signatures') {
      ensureVerticalSpace(56)
      currentY -= 12
      drawTextLine(block.leftLabel, MARGIN_X, currentY, 'F2', 9.5, [0.15, 0.18, 0.24])
      drawTextLine(block.leftName, MARGIN_X, currentY - 14, 'F1', 9, [0.25, 0.28, 0.34])

      if (block.rightLabel) {
        const rightX = MARGIN_X + CONTENT_WIDTH / 2 + 16
        drawTextLine(block.rightLabel, rightX, currentY, 'F2', 9.5, [0.15, 0.18, 0.24])

        if (block.rightName) {
          drawTextLine(block.rightName, rightX, currentY - 14, 'F1', 9, [0.25, 0.28, 0.34])
        }
      }

      currentY -= 42
    }
  }

  // Add footer with page numbering on every page
  const totalPages = pages.length
  pages.forEach((cmds, pageIdx) => {
    const footerText = `${doc.title} — Page ${pageIdx + 1} / ${totalPages}`
    cmds.push(
      `BT /F1 8 Tf 0.45 0.48 0.54 rg ${MARGIN_X} 32 Td (${encodePdfText(footerText)}) Tj ET`
    )
  })

  // Assemble PDF 1.4 object table
  // Obj 1: Catalog, Obj 2: Pages, Obj 3: Font F1 (Helvetica), Obj 4: Font F2 (Helvetica-Bold)
  // For each page i: Page object = 5 + i*2, Content stream = 6 + i*2
  const objects: string[] = []
  const pageObjNums: number[] = []

  objects.push('1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj')
  objects.push('') // placeholder for 2 0 obj (Pages)
  objects.push(
    '3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj'
  )
  objects.push(
    '4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj'
  )

  pages.forEach((cmds, idx) => {
    const pageObjNum = 5 + idx * 2
    const streamObjNum = 6 + idx * 2
    pageObjNums.push(pageObjNum)

    const streamContent = cmds.join('\n')
    objects.push(
      `${pageObjNum} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${A4_WIDTH} ${A4_HEIGHT}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${streamObjNum} 0 R >>\nendobj`
    )
    objects.push(
      `${streamObjNum} 0 obj\n<< /Length ${streamContent.length} >>\nstream\n${streamContent}\nendstream\nendobj`
    )
  })

  objects[1] = `2 0 obj\n<< /Type /Pages /Kids [${pageObjNums.map(n => `${n} 0 R`).join(' ')}] /Count ${pageObjNums.length} >>\nendobj`

  let pdfBody = '%PDF-1.4\n%\xE2\xE3\xCF\xD3\n'
  const offsets: number[] = [0]

  for (const obj of objects) {
    offsets.push(pdfBody.length)
    pdfBody += `${obj}\n`
  }

  const xrefOffset = pdfBody.length
  pdfBody += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`

  for (let i = 1; i <= objects.length; i++) {
    const off = offsets[i] ?? 0
    pdfBody += `${String(off).padStart(10, '0')} 00000 n \n`
  }

  pdfBody += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`

  const bytes = new Uint8Array(pdfBody.length)

  for (let i = 0; i < pdfBody.length; i++) {
    bytes[i] = pdfBody.charCodeAt(i) & 0xff
  }

  return bytes
}
