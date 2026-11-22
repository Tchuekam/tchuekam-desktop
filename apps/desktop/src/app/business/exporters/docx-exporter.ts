import type { BusinessDocument } from '../types'

import { serializeBusinessDocument } from './document-serializer'
import { buildZipArchive, escapeXml } from './zip-builder'

function paragraphXml(
  text: string,
  options?: { bold?: boolean; colorHex?: string; sizeHalfPts?: number; spacingAfter?: number }
): string {
  const boldTag = options?.bold ? '<w:b/>' : ''
  const sizeTag = options?.sizeHalfPts ? `<w:sz w:val="${options.sizeHalfPts}"/>` : '<w:sz w:val="21"/>'

  const colorTag = options?.colorHex
    ? `<w:color w:val="${options.colorHex.replace('#', '')}"/>`
    : ''

  const spacingAfter = options?.spacingAfter ?? 120

  return `<w:p><w:pPr><w:spacing w:after="${spacingAfter}"/></w:pPr><w:r><w:rPr>${boldTag}${sizeTag}${colorTag}</w:rPr><w:t xml:space="preserve">${escapeXml(text)}</w:t></w:r></w:p>`
}

function tableXml(headers: string[], rows: string[][]): string {
  const headerCells = headers
    .map(
      h =>
        `<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="EEF2FF"/></w:tcPr>${paragraphXml(h, { bold: true, sizeHalfPts: 19, spacingAfter: 60 })}</w:tc>`
    )
    .join('')

  const bodyRows = rows
    .map(
      row =>
        `<w:tr>${row
          .map(cell => `<w:tc>${paragraphXml(cell, { sizeHalfPts: 19, spacingAfter: 60 })}</w:tc>`)
          .join('')}</w:tr>`
    )
    .join('')

  return `<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/></w:tblBorders></w:tblPr><w:tr>${headerCells}</w:tr>${bodyRows}</w:tbl>`
}

/**
 * Generates a valid OpenXML (.docx) Word document archive with A4 page dimensions,
 * styled headings, bullet lists, and bordered financial/data tables.
 */
export function generateDocxBytes(doc: BusinessDocument): Uint8Array {
  const blocks = serializeBusinessDocument(doc)
  const bodyParts: string[] = []

  for (const block of blocks) {
    if (block.type === 'header') {
      bodyParts.push(
        paragraphXml(block.title, {
          bold: true,
          colorHex: block.accentColor,
          sizeHalfPts: 36,
          spacingAfter: 80
        })
      )

      if (block.subtitle) {
        bodyParts.push(
          paragraphXml(block.subtitle, {
            colorHex: '475569',
            sizeHalfPts: 20,
            spacingAfter: 200
          })
        )
      }
    } else if (block.type === 'heading') {
      bodyParts.push(
        paragraphXml(block.text, {
          bold: true,
          colorHex: block.level === 1 ? '0F172A' : '334155',
          sizeHalfPts: block.level === 1 ? 26 : 22,
          spacingAfter: 100
        })
      )
    } else if (block.type === 'paragraph') {
      bodyParts.push(paragraphXml(block.text, { sizeHalfPts: 21, spacingAfter: 120 }))
    } else if (block.type === 'bullets') {
      for (const item of block.items) {
        bodyParts.push(paragraphXml(`• ${item}`, { sizeHalfPts: 21, spacingAfter: 80 }))
      }
    } else if (block.type === 'keyValueGrid') {
      for (const pair of block.pairs) {
        bodyParts.push(
          paragraphXml(`${pair.label}: ${pair.value}`, {
            bold: false,
            sizeHalfPts: 20,
            spacingAfter: 80
          })
        )
      }
    } else if (block.type === 'callout') {
      bodyParts.push(
        paragraphXml(block.text, {
          bold: true,
          colorHex: block.kind === 'warning' ? '92400E' : '1E40AF',
          sizeHalfPts: 20,
          spacingAfter: 140
        })
      )
    } else if (block.type === 'table') {
      bodyParts.push(tableXml(block.headers, block.rows))
      bodyParts.push(paragraphXml('', { spacingAfter: 120 }))
    } else if (block.type === 'signatures') {
      const sigLine = block.rightLabel
        ? `${block.leftLabel}: ${block.leftName}          |          ${block.rightLabel}: ${block.rightName ?? ''}`
        : `${block.leftLabel}: ${block.leftName}`

      bodyParts.push(paragraphXml(sigLine, { bold: true, sizeHalfPts: 21, spacingAfter: 200 }))
    }
  }

  const contentTypesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`

  const relsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`

  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${bodyParts.join('\n    ')}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>`

  return buildZipArchive([
    { content: contentTypesXml, path: '[Content_Types].xml' },
    { content: relsXml, path: '_rels/.rels' },
    { content: documentXml, path: 'word/document.xml' }
  ])
}
