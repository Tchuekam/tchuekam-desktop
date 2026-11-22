import type {
  BusinessDocument,
  BusinessPlanData,
  InvoiceData,
  QuoteData
} from '../types'
import {
  calculateBusinessPlanProjections,
  calculateLineItemsSummary
} from '../utils/calculations'

import { buildZipArchive, escapeXml } from './zip-builder'

type CellValue = string | number

function colLetter(colIdx: number): string {
  let n = colIdx + 1
  let result = ''

  while (n > 0) {
    const rem = (n - 1) % 26
    result = String.fromCharCode(65 + rem) + result
    n = Math.floor((n - 1) / 26)
  }

  return result
}

function buildSheetXml(rows: CellValue[][]): string {
  const rowXml = rows
    .map((cells, rIdx) => {
      const rowNum = rIdx + 1

      const cellTags = cells
        .map((val, cIdx) => {
          const ref = `${colLetter(cIdx)}${rowNum}`

          if (typeof val === 'number' && Number.isFinite(val)) {
            return `<c r="${ref}" t="n"><v>${val}</v></c>`
          }

          return `<c r="${ref}" t="inlineStr"><is><t>${escapeXml(String(val ?? ''))}</t></is></c>`
        })
        .join('')

      return `<row r="${rowNum}">${cellTags}</row>`
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
 * Generates a standards-compliant OpenXML (.xlsx) Excel workbook for Invoices,
 * Quotations, and Business Plan 3-year financial models.
 */
export function generateXlsxBytes(doc: BusinessDocument): Uint8Array {
  const rows: CellValue[][] = []
  const isFr = doc.language === 'fr'

  if (doc.type === 'invoice' || doc.type === 'quote') {
    const inv = doc.data as InvoiceData & QuoteData
    const isInvoice = doc.type === 'invoice'
    const number = isInvoice ? (inv as InvoiceData).invoiceNumber : (inv as QuoteData).quoteNumber

    const summary = calculateLineItemsSummary(
      inv.items,
      isInvoice ? (inv as InvoiceData).amountPaid : 0
    )

    rows.push([doc.title, number])
    rows.push([isFr ? 'Émetteur' : 'Seller', inv.seller.companyName])
    rows.push([isFr ? 'Client' : 'Client', inv.client.companyName || inv.client.name])
    rows.push([isFr ? 'Devise' : 'Currency', inv.currency])
    rows.push([])
    rows.push([
      isFr ? 'Désignation' : 'Description',
      isFr ? 'Quantité' : 'Quantity',
      isFr ? 'Prix Unitaire' : 'Unit Price',
      isFr ? 'Remise %' : 'Discount %',
      isFr ? 'TVA %' : 'Tax %',
      isFr ? 'Total HT Net' : 'Net Subtotal',
      isFr ? 'Montant TVA' : 'Tax Amount',
      isFr ? 'Total TTC' : 'Line Total'
    ])

    inv.items.forEach((item, idx) => {
      const comp = summary.computedLines[idx]
      rows.push([
        item.description,
        item.quantity,
        item.unitPrice,
        item.discountPercent,
        item.taxRatePercent,
        comp?.netAmount ?? 0,
        comp?.taxAmount ?? 0,
        comp?.totalAmount ?? 0
      ])
    })

    rows.push([])
    rows.push([isFr ? 'Sous-total HT' : 'Subtotal', summary.subtotal])
    rows.push([isFr ? 'Remise Totale' : 'Total Discount', summary.discountTotal])
    rows.push([isFr ? 'Total TVA' : 'Total Tax', summary.taxTotal])
    rows.push([isFr ? 'TOTAL TTC' : 'GRAND TOTAL', summary.grandTotal])

    if (isInvoice) {
      rows.push([isFr ? 'Montant Payé' : 'Amount Paid', (inv as InvoiceData).amountPaid])
      rows.push([isFr ? 'Net à Payer' : 'Balance Due', summary.balanceDue])
    }
  } else if (doc.type === 'plan') {
    const plan = doc.data as BusinessPlanData
    const proj = calculateBusinessPlanProjections(plan.financialAssumptions)

    rows.push([`${plan.companyName} — 3-Year Financial Model (${plan.currency})`])
    rows.push([])
    rows.push([isFr ? 'Hypothèses' : 'Assumptions', isFr ? 'Valeur' : 'Value'])
    rows.push([isFr ? 'Investissement Initial' : 'Initial Investment', plan.financialAssumptions.initialInvestment])
    rows.push([isFr ? 'Charges Fixes Mensuelles' : 'Monthly Fixed Costs', plan.financialAssumptions.monthlyFixedCosts])
    rows.push([isFr ? 'Prix Unitaire Moyen' : 'Unit Price', plan.financialAssumptions.unitPrice])
    rows.push([isFr ? 'Coût Variable Unitaire' : 'Unit Variable Cost', plan.financialAssumptions.unitVariableCost])
    rows.push([isFr ? 'Volume Année 1' : 'Year 1 Units', plan.financialAssumptions.year1Units])
    rows.push([isFr ? 'Croissance Année 2 (%)' : 'Year 2 Growth (%)', plan.financialAssumptions.year2GrowthPercent])
    rows.push([isFr ? 'Croissance Année 3 (%)' : 'Year 3 Growth (%)', plan.financialAssumptions.year3GrowthPercent])
    rows.push([isFr ? 'Taux d’Imposition (%)' : 'Tax Rate (%)', plan.financialAssumptions.taxRatePercent])
    rows.push([isFr ? 'Seuil de Rentabilité (Unités/An)' : 'Break-Even Units/Year', proj.breakEvenUnitsPerYear])
    rows.push([])
    rows.push([
      isFr ? 'Compte de Résultat Prévisionnel' : 'Projected Income Statement',
      isFr ? 'Année 1' : 'Year 1',
      isFr ? 'Année 2' : 'Year 2',
      isFr ? 'Année 3' : 'Year 3'
    ])
    rows.push([isFr ? 'Unités Vendues' : 'Units Sold', proj.years[0].units, proj.years[1].units, proj.years[2].units])
    rows.push([isFr ? 'Chiffre d’Affaires' : 'Revenue', proj.years[0].revenue, proj.years[1].revenue, proj.years[2].revenue])
    rows.push([isFr ? 'Coûts Variables (COGS)' : 'COGS', proj.years[0].cogs, proj.years[1].cogs, proj.years[2].cogs])
    rows.push([isFr ? 'Marge Brute' : 'Gross Profit', proj.years[0].grossProfit, proj.years[1].grossProfit, proj.years[2].grossProfit])
    rows.push([isFr ? 'Charges Fixes Annuelles' : 'Fixed Costs', proj.years[0].fixedCosts, proj.years[1].fixedCosts, proj.years[2].fixedCosts])
    rows.push(['EBITDA', proj.years[0].ebitda, proj.years[1].ebitda, proj.years[2].ebitda])
    rows.push([isFr ? 'Impôts' : 'Tax', proj.years[0].tax, proj.years[1].tax, proj.years[2].tax])
    rows.push([isFr ? 'Résultat Net' : 'Net Profit', proj.years[0].netProfit, proj.years[1].netProfit, proj.years[2].netProfit])
    rows.push([
      isFr ? 'Trésorerie Cumulée' : 'Cumulative Cash Flow',
      proj.years[0].cumulativeCashFlow,
      proj.years[1].cumulativeCashFlow,
      proj.years[2].cumulativeCashFlow
    ])
  } else {
    rows.push([doc.title])
    rows.push([JSON.stringify(doc.data)])
  }

  const contentTypesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`

  const rootRelsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`

  const workbookXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Model" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>`

  const workbookRelsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>`

  return buildZipArchive([
    { content: contentTypesXml, path: '[Content_Types].xml' },
    { content: rootRelsXml, path: '_rels/.rels' },
    { content: workbookXml, path: 'xl/workbook.xml' },
    { content: workbookRelsXml, path: 'xl/_rels/workbook.xml.rels' },
    { content: buildSheetXml(rows), path: 'xl/worksheets/sheet1.xml' }
  ])
}
