import type {
  ContractData,
  CurrencyCode,
  CVData,
  DocumentLanguage,
  FinancialAssumptions,
  LineItem
} from '../types'

export interface ComputedLineItem {
  discountAmount: number
  grossAmount: number
  id: string
  included: boolean
  netAmount: number
  taxAmount: number
  totalAmount: number
}

export interface LineItemsSummary {
  balanceDue: number
  computedLines: ComputedLineItem[]
  discountTotal: number
  grandTotal: number
  subtotal: number
  taxTotal: number
}

/**
 * Convert a decimal number to integer cents (1/100th of a unit) to eliminate
 * IEEE-754 floating-point drift during financial calculations.
 */
export function toCents(amount: number): number {
  if (!Number.isFinite(amount)) {
    return 0
  }

  return Math.round(amount * 100)
}

export function fromCents(cents: number): number {
  if (!Number.isFinite(cents)) {
    return 0
  }

  return Math.round(cents) / 100
}

/**
 * Deterministically calculate line item subtotals, discounts, taxes, and grand total
 * using integer-cent arithmetic.
 */
export function calculateLineItemsSummary(items: LineItem[], amountPaid = 0): LineItemsSummary {
  let subtotalCents = 0
  let discountTotalCents = 0
  let taxTotalCents = 0
  let grandTotalCents = 0

  const computedLines: ComputedLineItem[] = items.map(item => {
    const included = item.optional ? Boolean(item.selected) : true
    const qty = Math.max(0, Number.isFinite(item.quantity) ? item.quantity : 0)
    const unitCents = Math.max(0, toCents(item.unitPrice))
    const discountPct = Math.min(100, Math.max(0, Number.isFinite(item.discountPercent) ? item.discountPercent : 0))
    const taxPct = Math.max(0, Number.isFinite(item.taxRatePercent) ? item.taxRatePercent : 0)

    const grossCents = Math.round(qty * unitCents)
    const discountCents = Math.round((grossCents * discountPct) / 100)
    const netCents = Math.max(0, grossCents - discountCents)
    const taxCents = Math.round((netCents * taxPct) / 100)
    const totalCents = netCents + taxCents

    if (included) {
      subtotalCents += grossCents
      discountTotalCents += discountCents
      taxTotalCents += taxCents
      grandTotalCents += totalCents
    }

    return {
      discountAmount: fromCents(discountCents),
      grossAmount: fromCents(grossCents),
      id: item.id,
      included,
      netAmount: fromCents(netCents),
      taxAmount: fromCents(taxCents),
      totalAmount: fromCents(totalCents)
    }
  })

  const paidCents = Math.max(0, toCents(amountPaid))
  const balanceDueCents = Math.max(0, grandTotalCents - paidCents)

  return {
    balanceDue: fromCents(balanceDueCents),
    computedLines,
    discountTotal: fromCents(discountTotalCents),
    grandTotal: fromCents(grandTotalCents),
    subtotal: fromCents(subtotalCents),
    taxTotal: fromCents(taxTotalCents)
  }
}

export function formatCurrency(
  amount: number,
  currency: CurrencyCode = 'XAF',
  language: DocumentLanguage = 'fr'
): string {
  const safe = Number.isFinite(amount) ? amount : 0

  if (currency === 'XAF') {
    const rounded = Math.round(safe)
    const formatted = rounded.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')

    return `${formatted} FCFA`
  }

  const fixed = safe.toFixed(2)
  const [intPart = '0', decPart = '00'] = fixed.split('.')

  if (currency === 'EUR') {
    const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, language === 'fr' ? ' ' : ',')

    return language === 'fr' ? `${grouped},${decPart} €` : `€${grouped}.${decPart}`
  }

  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')

  return `$${grouped}.${decPart}`
}

export function formatDocumentDate(dateStr: string, language: DocumentLanguage = 'fr'): string {
  const trimmed = (dateStr || '').trim()

  if (!trimmed) {
    return '[to confirm]'
  }

  const match = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/)

  if (!match) {
    return trimmed
  }

  const [, year, month, day] = match

  return language === 'fr' ? `${day}/${month}/${year}` : `${year}-${month}-${day}`
}

export function generateDocumentNumber(prefix: 'INV' | 'DEV' | 'ATT' | 'CTR', existingCount = 0): string {
  const datePart = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const seq = String(existingCount + 1).padStart(3, '0')

  return `${prefix}-${datePart}-${seq}`
}

export interface YearlyProjection {
  cogs: number
  cumulativeCashFlow: number
  ebitda: number
  fixedCosts: number
  grossMarginPercent: number
  grossProfit: number
  netProfit: number
  revenue: number
  tax: number
  units: number
  year: number
}

export interface BusinessPlanProjectionSummary {
  breakEvenUnitsPerYear: number
  contributionMarginPerUnit: number
  years: [YearlyProjection, YearlyProjection, YearlyProjection]
}

export function calculateBusinessPlanProjections(
  assumptions: FinancialAssumptions
): BusinessPlanProjectionSummary {
  const unitPrice = Math.max(0, assumptions.unitPrice || 0)
  const unitVarCost = Math.max(0, assumptions.unitVariableCost || 0)
  const annualFixed = Math.max(0, (assumptions.monthlyFixedCosts || 0) * 12)
  const taxRate = Math.min(100, Math.max(0, assumptions.taxRatePercent || 0))
  const initialInv = Math.max(0, assumptions.initialInvestment || 0)

  const y1Units = Math.max(0, Math.round(assumptions.year1Units || 0))
  const y2Units = Math.max(0, Math.round(y1Units * (1 + (assumptions.year2GrowthPercent || 0) / 100)))
  const y3Units = Math.max(0, Math.round(y2Units * (1 + (assumptions.year3GrowthPercent || 0) / 100)))

  const contribution = unitPrice - unitVarCost
  const breakEvenUnitsPerYear = contribution > 0 ? Math.ceil(annualFixed / contribution) : 0

  let cumulative = -toCents(initialInv)

  const buildYear = (year: number, units: number): YearlyProjection => {
    const revCents = Math.round(units * toCents(unitPrice))
    const cogsCents = Math.round(units * toCents(unitVarCost))
    const grossCents = revCents - cogsCents
    const fixedCents = toCents(annualFixed)
    const ebitdaCents = grossCents - fixedCents
    const taxCents = ebitdaCents > 0 ? Math.round((ebitdaCents * taxRate) / 100) : 0
    const netCents = ebitdaCents - taxCents
    cumulative += netCents

    const grossMarginPercent = revCents > 0 ? Math.round((grossCents / revCents) * 1000) / 10 : 0

    return {
      cogs: fromCents(cogsCents),
      cumulativeCashFlow: fromCents(cumulative),
      ebitda: fromCents(ebitdaCents),
      fixedCosts: fromCents(fixedCents),
      grossMarginPercent,
      grossProfit: fromCents(grossCents),
      netProfit: fromCents(netCents),
      revenue: fromCents(revCents),
      tax: fromCents(taxCents),
      units,
      year
    }
  }

  return {
    breakEvenUnitsPerYear,
    contributionMarginPerUnit: fromCents(toCents(unitPrice) - toCents(unitVarCost)),
    years: [buildYear(1, y1Units), buildYear(2, y2Units), buildYear(3, y3Units)]
  }
}

export interface CVATSAnalysis {
  checks: Array<{ label: string; passed: boolean; suggestion: string }>
  matchedKeywords: string[]
  missingKeywords: string[]
  score: number
}

const STOPWORDS = new Set([
  'the',
  'and',
  'for',
  'with',
  'that',
  'this',
  'from',
  'your',
  'have',
  'will',
  'are',
  'our',
  'you',
  'into',
  'dans',
  'pour',
  'avec',
  'une',
  'des',
  'les',
  'aux',
  'sur',
  'par',
  'plus',
  'vous',
  'nous',
  'sont',
  'etre',
  'avoir'
])

export function analyzeCvAtsReadiness(cv: CVData): CVATSAnalysis {
  const hasContact = Boolean(cv.fullName.trim() && cv.email.trim() && cv.phone.trim() && cv.location.trim())
  const summaryWords = cv.summary.trim().split(/\s+/).filter(Boolean).length
  const hasStrongSummary = summaryWords >= 20 && summaryWords <= 120
  const allBullets = cv.experience.flatMap(exp => exp.achievements).filter(b => b.trim().length > 0)
  const quantifiedBullets = allBullets.filter(b => /\d+%|\d+\s*(?:\+|x|k|m|fcfa|€|\$|ans|years|clients|users|projects)/i.test(b))
  const hasQuantifiedImpact = allBullets.length >= 2 && quantifiedBullets.length >= 1
  const hasSkills = cv.skills.filter(s => s.trim().length > 0).length >= 5
  const hasEducation = cv.education.some(ed => Boolean(ed.institution.trim() && ed.degree.trim()))
  const noPlaceholders = !/\[to confirm\]/i.test(JSON.stringify(cv))

  const checks = [
    {
      label: 'Complete contact header (Name, Email, Phone, Location)',
      passed: hasContact,
      suggestion: 'Add your full name, email address, phone number, and city/country.'
    },
    {
      label: 'Targeted professional summary (20–120 words)',
      passed: hasStrongSummary,
      suggestion: 'Write a 2–4 sentence summary highlighting your core expertise and value proposition.'
    },
    {
      label: 'Quantified achievement bullets in experience',
      passed: hasQuantifiedImpact,
      suggestion: 'Include measurable outcomes (e.g., "+25% revenue", "reduced latency by 40%", "managed 12 clients").'
    },
    {
      label: 'Core skills list (5+ relevant skills)',
      passed: hasSkills,
      suggestion: 'List at least 5 specific technical, operational, or domain skills.'
    },
    {
      label: 'Structured education credentials',
      passed: hasEducation,
      suggestion: 'Include your institution name, degree/diploma, and completion year.'
    },
    {
      label: 'No unconfirmed [to confirm] placeholders remaining',
      passed: noPlaceholders,
      suggestion: 'Replace all [to confirm] markers with verified dates, names, or metrics.'
    }
  ]

  const cvCorpus = [
    cv.headline,
    cv.summary,
    cv.skills.join(' '),
    ...cv.experience.map(e => `${e.role} ${e.company} ${e.achievements.join(' ')}`),
    ...cv.projects.map(p => `${p.name} ${p.description}`)
  ]
    .join(' ')
    .toLowerCase()

  const jobTokens = (cv.targetJobDescription || '')
    .toLowerCase()
    .replace(/[^a-z0-9àâçéèêëîïôûùüÿñæœ+#-]/gi, ' ')
    .split(/\s+/)
    .filter(token => token.length >= 4 && !STOPWORDS.has(token))

  const uniqueJobKeywords = Array.from(new Set(jobTokens)).slice(0, 24)
  const matchedKeywords = uniqueJobKeywords.filter(kw => cvCorpus.includes(kw))
  const missingKeywords = uniqueJobKeywords.filter(kw => !cvCorpus.includes(kw))

  const passedCount = checks.filter(c => c.passed).length
  const baseScore = Math.round((passedCount / checks.length) * 75)

  const keywordScore =
    uniqueJobKeywords.length > 0
      ? Math.round((matchedKeywords.length / uniqueJobKeywords.length) * 25)
      : hasSkills && hasStrongSummary
        ? 20
        : 10

  return {
    checks,
    matchedKeywords,
    missingKeywords,
    score: Math.min(100, baseScore + keywordScore)
  }
}

export function auditContractWarnings(contract: ContractData): string[] {
  const warnings: string[] = []

  if (!contract.partyAName.trim() || !contract.partyBName.trim()) {
    warnings.push('One or both contracting party names are missing.')
  }

  if (!contract.scope.trim() || contract.scope.includes('[to confirm]')) {
    warnings.push('Scope of work / object of the agreement contains unconfirmed details.')
  }

  if (contract.category !== 'nda' && contract.compensationAmount <= 0) {
    warnings.push('Compensation amount is zero or not yet specified.')
  }

  if (!contract.terminationConditions.trim()) {
    warnings.push('Termination notice period and exit conditions should be explicitly defined.')
  }

  if (!contract.disputeResolution.trim() || !contract.governingLaw.trim()) {
    warnings.push('Governing law and dispute resolution jurisdiction require confirmation.')
  }

  for (const clause of contract.clauses) {
    if (clause.requiresLegalReview) {
      warnings.push(`Clause "${clause.title}" is flagged for professional legal review before signing.`)
    }

    if (clause.content.includes('[to confirm]')) {
      warnings.push(`Clause "${clause.title}" still contains [to confirm] placeholders.`)
    }
  }

  return warnings
}
