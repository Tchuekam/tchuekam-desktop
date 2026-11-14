import type { BusinessDocument, BusinessPlanData, InvoiceData, PitchDeckData, PitchSlide, QuoteData } from '../types'
import { calculateBusinessPlanProjections, calculateLineItemsSummary } from '../utils/calculations'

import { serializeBusinessDocument } from './document-serializer'
import { createZipArchive, escapeXml, type ZipEntryInput } from './zip'

interface RunStyleOptions {
  bold?: boolean
  colorHex?: string
  sizeHalfPts?: number
  spacingAfter?: number
}

function buildDocxParagraph(text: string, opts?: RunStyleOptions): string {
  const boldXml = opts?.bold ? '<w:b/>' : ''
  const sizeXml = opts?.sizeHalfPts ? `<w:sz w:val="${opts.sizeHalfPts}"/>` : '<w:sz w:val="21"/>'
  const colorXml = opts?.colorHex ? `<w:color w:val="${opts.colorHex.replace('#', '')}"/>` : ''

  return `<w:p><w:pPr><w:spacing w:after="${opts?.spacingAfter ?? 120}"/></w:pPr><w:r><w:rPr>${boldXml}${sizeXml}${colorXml}</w:rPr><w:t xml:space="preserve">${escapeXml(text)}</w:t></w:r></w:p>`
}

function buildDocxTable(headers: string[], rows: string[][]): string {
  const headerCells = headers
    .map(
      header =>
        `<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="EEF2FF"/></w:tcPr>${buildDocxParagraph(header, { bold: true, sizeHalfPts: 19, spacingAfter: 60 })}</w:tc>`
    )
    .join('')

  const bodyRows = rows
    .map(
      row =>
        `<w:tr>${row.map(cell => `<w:tc>${buildDocxParagraph(cell, { sizeHalfPts: 19, spacingAfter: 60 })}</w:tc>`).join('')}</w:tr>`
    )
    .join('')

  return `<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/></w:tblBorders></w:tblPr><w:tr>${headerCells}</w:tr>${bodyRows}</w:tbl>`
}

/**
 * Generate a Word (.docx) OOXML package from any BusinessDocument.
 */
export function buildDocxBytes(doc: BusinessDocument): Uint8Array {
  const blocks = serializeBusinessDocument(doc)
  const parts: string[] = []

  for (const block of blocks) {
    if (block.type === 'header') {
      parts.push(buildDocxParagraph(block.title, { bold: true, colorHex: block.accentColor, sizeHalfPts: 36, spacingAfter: 80 }))

      if (block.subtitle) {
        parts.push(buildDocxParagraph(block.subtitle, { colorHex: '475569', sizeHalfPts: 20, spacingAfter: 200 }))
      }
    } else if (block.type === 'heading') {
      parts.push(
        buildDocxParagraph(block.text, {
          bold: true,
          colorHex: block.level === 1 ? '0F172A' : '334155',
          sizeHalfPts: block.level === 1 ? 26 : 22,
          spacingAfter: 100
        })
      )
    } else if (block.type === 'paragraph') {
      parts.push(buildDocxParagraph(block.text, { sizeHalfPts: 21, spacingAfter: 120 }))
    } else if (block.type === 'bullets') {
      for (const item of block.items) {
        parts.push(buildDocxParagraph(`• ${item}`, { sizeHalfPts: 21, spacingAfter: 80 }))
      }
    } else if (block.type === 'keyValueGrid') {
      for (const pair of block.pairs) {
        parts.push(buildDocxParagraph(`${pair.label}: ${pair.value}`, { bold: false, sizeHalfPts: 20, spacingAfter: 80 }))
      }
    } else if (block.type === 'callout') {
      parts.push(
        buildDocxParagraph(block.text, {
          bold: true,
          colorHex: block.kind === 'warning' ? '92400E' : '1E40AF',
          sizeHalfPts: 20,
          spacingAfter: 140
        })
      )
    } else if (block.type === 'table') {
      parts.push(buildDocxTable(block.headers, block.rows), buildDocxParagraph('', { spacingAfter: 120 }))
    } else if (block.type === 'signatures') {
      const line = block.rightLabel
        ? `${block.leftLabel}: ${block.leftName}          |          ${block.rightLabel}: ${block.rightName ?? ''}`
        : `${block.leftLabel}: ${block.leftName}`

      parts.push(buildDocxParagraph(line, { bold: true, sizeHalfPts: 21, spacingAfter: 200 }))
    }
  }

  return createZipArchive([
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`,
      path: '[Content_Types].xml'
    },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`,
      path: '_rels/.rels'
    },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${parts.join('\n    ')}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>`,
      path: 'word/document.xml'
    }
  ])
}

function buildPptSlideXml(slide: PitchSlide, companyTitle: string, index: number, total: number): string {
  const bulletParagraphs = slide.bullets
    .map(
      bullet => `<a:p>
            <a:r>
              <a:rPr lang="fr-FR" sz="2000" dirty="0"><a:solidFill><a:srgbClr val="1E293B"/></a:solidFill></a:rPr>
              <a:t>• ${escapeXml(bullet)}</a:t>
            </a:r>
          </a:p>`
    )
    .join('\n          ')

  const metricParagraph =
    slide.metricLabel && slide.metricValue
      ? `<a:p>
            <a:r>
              <a:rPr lang="fr-FR" sz="2200" b="1" dirty="0"><a:solidFill><a:srgbClr val="0053FD"/></a:solidFill></a:rPr>
              <a:t>${escapeXml(`${slide.metricLabel}: ${slide.metricValue}`)}</a:t>
            </a:r>
          </a:p>`
      : ''

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="2" name="Title"/>
          <p:cNvSpPr/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm>
            <a:off x="685800" y="457200"/>
            <a:ext cx="10820400" cy="1371600"/>
          </a:xfrm>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/>
          <a:lstStyle/>
          <a:p>
            <a:r>
              <a:rPr lang="fr-FR" sz="3200" b="1" dirty="0"><a:solidFill><a:srgbClr val="0F172A"/></a:solidFill></a:rPr>
              <a:t>${escapeXml(slide.title)}</a:t>
            </a:r>
          </a:p>
          <a:p>
            <a:r>
              <a:rPr lang="fr-FR" sz="1800" dirty="0"><a:solidFill><a:srgbClr val="475569"/></a:solidFill></a:rPr>
              <a:t>${escapeXml(slide.subtitle)}</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="3" name="Content"/>
          <p:cNvSpPr/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm>
            <a:off x="685800" y="1981200"/>
            <a:ext cx="10820400" cy="4114800"/>
          </a:xfrm>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/>
          <a:lstStyle/>
          ${metricParagraph}
          ${bulletParagraphs}
          <a:p>
            <a:r>
              <a:rPr lang="fr-FR" sz="1200" dirty="0"><a:solidFill><a:srgbClr val="94A3B8"/></a:solidFill></a:rPr>
              <a:t>${escapeXml(`${companyTitle} · Slide ${index}/${total}`)}</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>`
}

/**
 * Generate a widescreen 16:9 PowerPoint (.pptx) deck package.
 */
export function buildPptxBytes(doc: BusinessDocument): Uint8Array {
  const deck = doc.data as PitchDeckData
  const slides: PitchSlide[] =
    Array.isArray(deck.slides) && deck.slides.length > 0
      ? deck.slides
      : [
          {
            bullets: [doc.title],
            id: 'slide-1',
            key: 'problem',
            layout: 'hero',
            metricLabel: '',
            metricValue: '',
            speakerNotes: '',
            subtitle: '',
            title: doc.title
          }
        ]

  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  ${slides.map((_, idx) => `<Override PartName="/ppt/slides/slide${idx + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`).join('\n  ')}
</Types>`

  const presentationXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst>
    <p:sldMasterId id="2147483648" r:id="rId1"/>
  </p:sldMasterIdLst>
  <p:sldIdLst>
    ${slides.map((_, idx) => `<p:sldId id="${256 + idx}" r:id="rId${idx + 2}"/>`).join('\n    ')}
  </p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>`

  const presentationRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  ${slides.map((_, idx) => `<Relationship Id="rId${idx + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide${idx + 1}.xml"/>`).join('\n  ')}
</Relationships>`

  const entries: ZipEntryInput[] = [
    { content: contentTypes, path: '[Content_Types].xml' },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>`,
      path: '_rels/.rels'
    },
    { content: presentationXml, path: 'ppt/presentation.xml' },
    { content: presentationRels, path: 'ppt/_rels/presentation.xml.rels' },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
</p:sldMaster>`,
      path: 'ppt/slideMasters/slideMaster1.xml'
    },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>`,
      path: 'ppt/slideMasters/_rels/slideMaster1.xml.rels'
    },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
</p:sldLayout>`,
      path: 'ppt/slideLayouts/slideLayout1.xml'
    },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>`,
      path: 'ppt/slideLayouts/_rels/slideLayout1.xml.rels'
    }
  ]

  slides.forEach((slide, idx) => {
    entries.push(
      {
        content: buildPptSlideXml(slide, deck.companyName || doc.title, idx + 1, slides.length),
        path: `ppt/slides/slide${idx + 1}.xml`
      },
      {
        content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>`,
        path: `ppt/slides/_rels/slide${idx + 1}.xml.rels`
      }
    )
  })

  return createZipArchive(entries)
}

function columnLetters(colIndex: number): string {
  let n = colIndex + 1
  let label = ''

  while (n > 0) {
    const rem = (n - 1) % 26

    label = String.fromCharCode(65 + rem) + label
    n = Math.floor((n - 1) / 26)
  }

  return label
}

function buildWorksheetXml(rows: Array<Array<string | number>>): string {
  const rowXml = rows
    .map((row, rIdx) => {
      const rowNum = rIdx + 1
      const cellsXml = row
        .map((cell, cIdx) => {
          const ref = `${columnLetters(cIdx)}${rowNum}`

          return typeof cell === 'number' && Number.isFinite(cell)
            ? `<c r="${ref}" t="n"><v>${cell}</v></c>`
            : `<c r="${ref}" t="inlineStr"><is><t>${escapeXml(String(cell ?? ''))}</t></is></c>`
        })
        .join('')

      return `<row r="${rowNum}">${cellsXml}</row>`
    })
    .join('\n    ')

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    ${rowXml}
  </sheetData>
</worksheet>`
}

/**
 * Generate an Excel (.xlsx) workbook from commercial financials, 3-year projections, or raw tabular fallback.
 */
export function buildXlsxBytes(doc: BusinessDocument): Uint8Array {
  const rows: Array<Array<string | number>> = []
  const isFr = doc.language === 'fr'

  if (doc.type === 'invoice' || doc.type === 'quote') {
    const isInvoice = doc.type === 'invoice'
    const inv = isInvoice ? (doc.data as InvoiceData) : null
    const qt = !isInvoice ? (doc.data as QuoteData) : null
    const shared = inv ?? qt

    if (shared) {
      const number = inv ? inv.invoiceNumber : qt ? qt.quoteNumber : ''
      const amountPaid = inv ? inv.amountPaid : 0
      const summary = calculateLineItemsSummary(shared.items, amountPaid)

      rows.push(
        [doc.title, number],
        [isFr ? 'Émetteur' : 'Seller', shared.seller.companyName],
        ['Client', shared.client.companyName || shared.client.name],
        [isFr ? 'Devise' : 'Currency', shared.currency],
        [],
        [
          isFr ? 'Désignation' : 'Description',
          isFr ? 'Quantité' : 'Quantity',
          isFr ? 'Prix Unitaire' : 'Unit Price',
          isFr ? 'Remise %' : 'Discount %',
          isFr ? 'TVA %' : 'Tax %',
          isFr ? 'Total HT Net' : 'Net Subtotal',
          isFr ? 'Montant TVA' : 'Tax Amount',
          isFr ? 'Total TTC' : 'Line Total'
        ]
      )

      shared.items.forEach((item, idx) => {
        const line = summary.computedLines[idx]

        rows.push([
          item.description,
          item.quantity,
          item.unitPrice,
          item.discountPercent,
          item.taxRatePercent,
          line?.netAmount ?? 0,
          line?.taxAmount ?? 0,
          line?.totalAmount ?? 0
        ])
      })

      rows.push(
        [],
        [isFr ? 'Sous-total HT' : 'Subtotal', summary.subtotal],
        [isFr ? 'Remise Totale' : 'Total Discount', summary.discountTotal],
        [isFr ? 'Total TVA' : 'Total Tax', summary.taxTotal],
        [isFr ? 'TOTAL TTC' : 'GRAND TOTAL', summary.grandTotal]
      )

      if (inv) {
        rows.push(
          [isFr ? 'Montant Payé' : 'Amount Paid', inv.amountPaid],
          [isFr ? 'Net à Payer' : 'Balance Due', summary.balanceDue]
        )
      }
    }
  } else if (doc.type === 'plan') {
    const plan = doc.data as BusinessPlanData
    const proj = calculateBusinessPlanProjections(plan.financialAssumptions)
    const [y1, y2, y3] = proj.years

    rows.push(
      [`${plan.companyName} — 3-Year Financial Model (${plan.currency})`],
      [],
      [isFr ? 'Hypothèses' : 'Assumptions', isFr ? 'Valeur' : 'Value'],
      [isFr ? 'Investissement Initial' : 'Initial Investment', plan.financialAssumptions.initialInvestment],
      [isFr ? 'Charges Fixes Mensuelles' : 'Monthly Fixed Costs', plan.financialAssumptions.monthlyFixedCosts],
      [isFr ? 'Prix Unitaire Moyen' : 'Unit Price', plan.financialAssumptions.unitPrice],
      [isFr ? 'Coût Variable Unitaire' : 'Unit Variable Cost', plan.financialAssumptions.unitVariableCost],
      [isFr ? 'Volume Année 1' : 'Year 1 Units', plan.financialAssumptions.year1Units],
      [isFr ? 'Croissance Année 2 (%)' : 'Year 2 Growth (%)', plan.financialAssumptions.year2GrowthPercent],
      [isFr ? 'Croissance Année 3 (%)' : 'Year 3 Growth (%)', plan.financialAssumptions.year3GrowthPercent],
      [isFr ? 'Taux d’Imposition (%)' : 'Tax Rate (%)', plan.financialAssumptions.taxRatePercent],
      [isFr ? 'Seuil de Rentabilité (Unités/An)' : 'Break-Even Units/Year', proj.breakEvenUnitsPerYear],
      [],
      [isFr ? 'Compte de Résultat Prévisionnel' : 'Projected Income Statement', isFr ? 'Année 1' : 'Year 1', isFr ? 'Année 2' : 'Year 2', isFr ? 'Année 3' : 'Year 3'],
      [isFr ? 'Unités Vendues' : 'Units Sold', y1.units, y2.units, y3.units],
      [isFr ? 'Chiffre d’Affaires' : 'Revenue', y1.revenue, y2.revenue, y3.revenue],
      [isFr ? 'Coûts Variables (COGS)' : 'COGS', y1.cogs, y2.cogs, y3.cogs],
      [isFr ? 'Marge Brute' : 'Gross Profit', y1.grossProfit, y2.grossProfit, y3.grossProfit],
      [isFr ? 'Charges Fixes Annuelles' : 'Fixed Costs', y1.fixedCosts, y2.fixedCosts, y3.fixedCosts],
      ['EBITDA', y1.ebitda, y2.ebitda, y3.ebitda],
      [isFr ? 'Impôts' : 'Tax', y1.tax, y2.tax, y3.tax],
      [isFr ? 'Résultat Net' : 'Net Profit', y1.netProfit, y2.netProfit, y3.netProfit],
      [isFr ? 'Trésorerie Cumulée' : 'Cumulative Cash Flow', y1.cumulativeCashFlow, y2.cumulativeCashFlow, y3.cumulativeCashFlow]
    )
  } else {
    rows.push([doc.title], [JSON.stringify(doc.data)])
  }

  return createZipArchive([
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`,
      path: '[Content_Types].xml'
    },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`,
      path: '_rels/.rels'
    },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Model" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>`,
      path: 'xl/workbook.xml'
    },
    {
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>`,
      path: 'xl/_rels/workbook.xml.rels'
    },
    { content: buildWorksheetXml(rows), path: 'xl/worksheets/sheet1.xml' }
  ])
}
