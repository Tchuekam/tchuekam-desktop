import { ALL_TEMPLATES } from '../schemas'
import type {
  AttestationData,
  BusinessDocument,
  BusinessPlanData,
  BusinessPlanSectionKey,
  ContractData,
  CoverLetterData,
  CVData,
  InvoiceData,
  PitchDeckData,
  QuoteData,
  ScanDocumentData
} from '../types'
import {
  auditContractWarnings,
  calculateBusinessPlanProjections,
  calculateLineItemsSummary,
  formatCurrency,
  formatDocumentDate
} from '../utils/calculations'

export interface HeaderBlock {
  accentColor: string
  subtitle: string
  title: string
  type: 'header'
}

export interface HeadingBlock {
  level: 1 | 2
  text: string
  type: 'heading'
}

export interface ParagraphBlock {
  text: string
  type: 'paragraph'
}

export interface BulletsBlock {
  items: string[]
  type: 'bullets'
}

export interface KeyValuePair {
  label: string
  value: string
}

export interface KeyValueGridBlock {
  pairs: KeyValuePair[]
  type: 'keyValueGrid'
}

export interface CalloutBlock {
  kind: 'info' | 'warning'
  text: string
  type: 'callout'
}

export interface TableBlock {
  headers: string[]
  rows: string[][]
  type: 'table'
}

export interface SignaturesBlock {
  leftLabel: string
  leftName: string
  rightLabel?: string
  rightName?: string
  type: 'signatures'
}

export type SerializedBlock =
  | HeaderBlock
  | HeadingBlock
  | ParagraphBlock
  | BulletsBlock
  | KeyValueGridBlock
  | CalloutBlock
  | TableBlock
  | SignaturesBlock

const PLAN_SECTION_KEYS: BusinessPlanSectionKey[] = [
  'executiveSummary',
  'companyOverview',
  'problem',
  'solution',
  'marketAnalysis',
  'competitiveAnalysis',
  'productsServices',
  'businessModel',
  'marketingStrategy',
  'operations',
  'managementTeam',
  'financialProjections',
  'fundingRequirements',
  'riskAnalysis'
]

const PLAN_TITLES_FR: Record<BusinessPlanSectionKey, string> = {
  businessModel: '8. Modèle Économique',
  companyOverview: '2. Présentation de l’Entreprise',
  competitiveAnalysis: '6. Analyse Concurrentielle',
  executiveSummary: '1. Synthèse Exécutive',
  financialProjections: '12. Projections Financières',
  fundingRequirements: '13. Besoins de Financement',
  managementTeam: '11. Équipe Dirigeante',
  marketAnalysis: '5. Analyse du Marché',
  marketingStrategy: '9. Stratégie Marketing & Commerciale',
  operations: '10. Plan Opérationnel',
  problem: '3. Problématique Client',
  productsServices: '7. Produits & Services',
  riskAnalysis: '14. Analyse des Risques',
  solution: '4. Solution Proposée'
}

const PLAN_TITLES_EN: Record<BusinessPlanSectionKey, string> = {
  businessModel: '8. Business Model',
  companyOverview: '2. Company Overview',
  competitiveAnalysis: '6. Competitive Analysis',
  executiveSummary: '1. Executive Summary',
  financialProjections: '12. Financial Projections',
  fundingRequirements: '13. Funding Requirements',
  managementTeam: '11. Management & Team',
  marketAnalysis: '5. Market Analysis',
  marketingStrategy: '9. Marketing & Sales Strategy',
  operations: '10. Operations Plan',
  problem: '3. Problem Statement',
  productsServices: '7. Products & Services',
  riskAnalysis: '14. Risk Analysis',
  solution: '4. Proposed Solution'
}

function serializeCv(
  doc: BusinessDocument,
  cv: CVData,
  accentColor: string,
  isFr: boolean
): SerializedBlock[] {
  const blocks: SerializedBlock[] = [
    {
      accentColor,
      subtitle: [cv.headline, cv.location, cv.email, cv.phone, cv.linkedin, cv.website]
        .filter(Boolean)
        .join(' · '),
      title: cv.fullName || doc.title,
      type: 'header'
    }
  ]

  for (const section of cv.sectionOrder) {
    if (section === 'summary' && cv.summary.trim()) {
      blocks.push(
        { level: 1, text: isFr ? 'Profil Professionnel' : 'Professional Summary', type: 'heading' },
        { text: cv.summary, type: 'paragraph' }
      )
    } else if (section === 'experience' && cv.experience.length > 0) {
      blocks.push({
        level: 1,
        text: isFr ? 'Expérience Professionnelle' : 'Work Experience',
        type: 'heading'
      })

      for (const exp of cv.experience) {
        const period = `${exp.startDate} – ${exp.current ? (isFr ? 'Présent' : 'Present') : exp.endDate}`

        blocks.push({
          level: 2,
          text: `${exp.role} — ${exp.company} (${exp.location || ''}, ${period})`,
          type: 'heading'
        })

        if (exp.achievements.length > 0) {
          blocks.push({ items: exp.achievements.filter(Boolean), type: 'bullets' })
        }
      }
    } else if (section === 'education' && cv.education.length > 0) {
      blocks.push({ level: 1, text: isFr ? 'Formation' : 'Education', type: 'heading' })

      for (const edu of cv.education) {
        blocks.push({
          text: `${edu.degree}${edu.field ? ` (${edu.field})` : ''} — ${edu.institution}, ${edu.location} (${edu.startDate} – ${edu.endDate})${edu.honors ? ` · ${edu.honors}` : ''}`,
          type: 'paragraph'
        })
      }
    } else if (section === 'skills' && cv.skills.length > 0) {
      blocks.push(
        { level: 1, text: isFr ? 'Compétences Clés' : 'Core Skills', type: 'heading' },
        { text: cv.skills.join(' · '), type: 'paragraph' }
      )
    } else if (section === 'languages' && cv.languages.length > 0) {
      blocks.push(
        { level: 1, text: isFr ? 'Langues' : 'Languages', type: 'heading' },
        { text: cv.languages.map(lang => `${lang.language} (${lang.level})`).join(' · '), type: 'paragraph' }
      )
    } else if (section === 'certifications' && cv.certifications.length > 0) {
      blocks.push(
        { level: 1, text: 'Certifications', type: 'heading' },
        {
          items: cv.certifications.map(cert => `${cert.name} — ${cert.issuer} (${cert.date})`),
          type: 'bullets'
        }
      )
    } else if (section === 'projects' && cv.projects.length > 0) {
      blocks.push({ level: 1, text: isFr ? 'Projets Réalisés' : 'Key Projects', type: 'heading' })

      for (const proj of cv.projects) {
        blocks.push({
          text: `${proj.name}${proj.role ? ` (${proj.role})` : ''}: ${proj.description}${proj.link ? ` [${proj.link}]` : ''}`,
          type: 'paragraph'
        })
      }
    } else if (section === 'volunteer' && cv.volunteer.trim()) {
      blocks.push(
        { level: 1, text: isFr ? 'Engagement & Bénévolat' : 'Volunteer Experience', type: 'heading' },
        { text: cv.volunteer, type: 'paragraph' }
      )
    } else if (section === 'references' && cv.references.trim()) {
      blocks.push(
        { level: 1, text: isFr ? 'Références' : 'References', type: 'heading' },
        { text: cv.references, type: 'paragraph' }
      )
    } else if (section === 'custom' && cv.customSections.length > 0) {
      for (const custom of cv.customSections) {
        blocks.push(
          { level: 1, text: custom.title, type: 'heading' },
          { text: custom.content, type: 'paragraph' }
        )
      }
    }
  }

  return blocks
}

function serializeCommercialDoc(
  doc: BusinessDocument,
  accentColor: string,
  isFr: boolean
): SerializedBlock[] {
  const isInvoice = doc.type === 'invoice'
  const invData = isInvoice ? (doc.data as InvoiceData) : null
  const quoteData = !isInvoice ? (doc.data as QuoteData) : null
  const shared = invData ?? quoteData

  if (!shared) {
    return []
  }

  const docNumber = invData ? invData.invoiceNumber : (quoteData?.quoteNumber ?? '')
  const dueOrValid = invData ? invData.dueDate : (quoteData?.validUntil ?? '')
  const amountPaid = invData ? invData.amountPaid : 0
  const summary = calculateLineItemsSummary(shared.items, amountPaid)

  const blocks: SerializedBlock[] = [
    {
      accentColor,
      subtitle: `${docNumber} · ${formatDocumentDate(shared.issueDate, doc.language)}`,
      title: isInvoice ? (isFr ? 'FACTURE' : 'INVOICE') : isFr ? 'DEVIS COMMERCIAL' : 'QUOTATION',
      type: 'header'
    },
    {
      pairs: [
        {
          label: isFr ? 'Émetteur' : 'From (Seller)',
          value: [
            shared.seller.companyName,
            shared.seller.address,
            shared.seller.phone,
            shared.seller.email,
            shared.seller.niu ? `NIU: ${shared.seller.niu}` : '',
            shared.seller.rccm ? `RCCM: ${shared.seller.rccm}` : ''
          ]
            .filter(Boolean)
            .join(' | ')
        },
        {
          label: isFr ? 'Client' : 'Bill To (Client)',
          value: [
            shared.client.companyName,
            shared.client.name,
            shared.client.address,
            shared.client.phone,
            shared.client.email
          ]
            .filter(Boolean)
            .join(' | ')
        },
        {
          label: isInvoice ? (isFr ? 'Échéance' : 'Due Date') : isFr ? 'Validité' : 'Valid Until',
          value: formatDocumentDate(dueOrValid, doc.language)
        },
        {
          label: isFr ? 'Conditions de règlement' : 'Payment Terms',
          value: `${shared.paymentTerms} (${shared.paymentMethod.toUpperCase()})`
        }
      ],
      type: 'keyValueGrid'
    }
  ]

  if (shared.description.trim()) {
    blocks.push({ text: shared.description, type: 'paragraph' })
  }

  blocks.push({
    headers: [
      isFr ? 'Désignation' : 'Description',
      isFr ? 'Qté' : 'Qty',
      isFr ? 'Prix Unitaire' : 'Unit Price',
      isFr ? 'Remise %' : 'Disc %',
      isFr ? 'TVA %' : 'Tax %',
      isFr ? 'Total TTC' : 'Line Total'
    ],
    rows: shared.items.map((item, idx) => {
      const computed = summary.computedLines[idx]
      const optSuffix = item.optional ? (item.selected ? ' [Option incluse]' : ' [Option exclue]') : ''

      return [
        `${item.description}${optSuffix}`,
        String(item.quantity),
        formatCurrency(item.unitPrice, shared.currency, doc.language),
        `${item.discountPercent}%`,
        `${item.taxRatePercent}%`,
        formatCurrency(computed?.totalAmount ?? 0, shared.currency, doc.language)
      ]
    }),
    type: 'table'
  })

  const summaryRows: string[][] = [
    [isFr ? 'Sous-total HT' : 'Subtotal', formatCurrency(summary.subtotal, shared.currency, doc.language)],
    [isFr ? 'Remise totale' : 'Total Discount', formatCurrency(summary.discountTotal, shared.currency, doc.language)],
    [isFr ? 'Total Taxes (TVA)' : 'Total Tax', formatCurrency(summary.taxTotal, shared.currency, doc.language)],
    [isFr ? 'TOTAL TTC' : 'GRAND TOTAL', formatCurrency(summary.grandTotal, shared.currency, doc.language)]
  ]

  if (isInvoice) {
    summaryRows.push(
      [isFr ? 'Montant payé' : 'Amount Paid', formatCurrency(amountPaid, shared.currency, doc.language)],
      [isFr ? 'NET À PAYER' : 'BALANCE DUE', formatCurrency(summary.balanceDue, shared.currency, doc.language)]
    )
  }

  blocks.push({
    headers: [isFr ? 'Récapitulatif Financier' : 'Financial Summary', isFr ? 'Montant' : 'Amount'],
    rows: summaryRows,
    type: 'table'
  })

  if (shared.paymentDetails.trim()) {
    blocks.push({
      kind: 'info',
      text: `${isFr ? 'Coordonnées de paiement' : 'Payment Instructions'}: ${shared.paymentDetails}`,
      type: 'callout'
    })
  }

  if (shared.notes.trim()) {
    blocks.push({ text: shared.notes, type: 'paragraph' })
  }

  blocks.push({
    leftLabel: isFr ? 'Pour l’Émetteur' : 'Authorized Signatory',
    leftName: shared.signatoryName || shared.seller.companyName,
    rightLabel: isInvoice ? undefined : isFr ? 'Bon pour accord (Client)' : 'Client Acceptance',
    rightName: isInvoice ? undefined : shared.client.name || shared.client.companyName,
    type: 'signatures'
  })

  return blocks
}

function serializeContract(
  doc: BusinessDocument,
  contract: ContractData,
  accentColor: string,
  isFr: boolean
): SerializedBlock[] {
  const warnings = auditContractWarnings(contract)
  const blocks: SerializedBlock[] = [
    {
      accentColor,
      subtitle: `${isFr ? 'Date d’effet' : 'Effective Date'}: ${formatDocumentDate(contract.effectiveDate, doc.language)} · ${contract.governingLaw}`,
      title: doc.title,
      type: 'header'
    },
    {
      kind: 'warning',
      text: isFr
        ? 'AVERTISSEMENT JURIDIQUE : Ce document est un projet généré à titre indicatif. Faites-le relire par un conseil juridique qualifié avant signature.'
        : 'LEGAL NOTICE: This document is an illustrative draft and does not constitute formal legal advice. Have qualified counsel review before execution.',
      type: 'callout'
    }
  ]

  if (warnings.length > 0) {
    blocks.push({ items: warnings, type: 'bullets' })
  }

  blocks.push(
    {
      pairs: [
        {
          label: isFr ? 'Partie A' : 'Party A',
          value: `${contract.partyAName} (${contract.partyAAddress}) — ${contract.partyARegistration}`
        },
        {
          label: isFr ? 'Partie B' : 'Party B',
          value: `${contract.partyBName} (${contract.partyBAddress}) — ${contract.partyBRegistration}`
        },
        { label: isFr ? 'Durée' : 'Duration', value: contract.duration },
        {
          label: isFr ? 'Rémunération' : 'Compensation',
          value: `${formatCurrency(contract.compensationAmount, contract.currency, doc.language)} — ${contract.paymentConditions}`
        }
      ],
      type: 'keyValueGrid'
    },
    { level: 1, text: isFr ? 'Objet & Périmètre' : 'Scope of Agreement', type: 'heading' },
    { text: contract.scope, type: 'paragraph' },
    { level: 1, text: isFr ? 'Responsabilités' : 'Responsibilities', type: 'heading' },
    { text: contract.responsibilities, type: 'paragraph' }
  )

  for (const clause of contract.clauses) {
    const suffix = clause.requiresLegalReview
      ? isFr
        ? ' [Revue juridique recommandée]'
        : ' [Legal review recommended]'
      : ''

    blocks.push(
      { level: 1, text: `${clause.title}${suffix}`, type: 'heading' },
      { text: clause.content, type: 'paragraph' }
    )
  }

  blocks.push(
    { level: 1, text: isFr ? 'Confidentialité' : 'Confidentiality', type: 'heading' },
    { text: contract.confidentiality, type: 'paragraph' },
    { level: 1, text: isFr ? 'Résiliation & Litiges' : 'Termination & Dispute Resolution', type: 'heading' },
    { text: `${contract.terminationConditions}\n${contract.disputeResolution}`, type: 'paragraph' },
    {
      leftLabel: isFr ? 'Pour la Partie A' : 'For Party A',
      leftName: contract.signatoryA || contract.partyAName,
      rightLabel: isFr ? 'Pour la Partie B' : 'For Party B',
      rightName: contract.signatoryB || contract.partyBName,
      type: 'signatures'
    }
  )

  return blocks
}

function serializePlan(
  doc: BusinessDocument,
  plan: BusinessPlanData,
  accentColor: string,
  isFr: boolean
): SerializedBlock[] {
  const proj = calculateBusinessPlanProjections(plan.financialAssumptions)
  const [y1, y2, y3] = proj.years
  const sectionTitles = isFr ? PLAN_TITLES_FR : PLAN_TITLES_EN
  const blocks: SerializedBlock[] = [
    {
      accentColor,
      subtitle: `${plan.companyName} · ${plan.industry} · ${plan.location}`,
      title: doc.title,
      type: 'header'
    }
  ]

  for (const key of PLAN_SECTION_KEYS) {
    blocks.push(
      { level: 1, text: sectionTitles[key], type: 'heading' },
      { text: plan.sections[key] || '[to confirm]', type: 'paragraph' }
    )

    if (key === 'financialProjections') {
      blocks.push({
        headers: [
          isFr ? 'Indicateur (Estimations Illustratives)' : 'Metric (Illustrative Estimate)',
          isFr ? 'Année 1' : 'Year 1',
          isFr ? 'Année 2' : 'Year 2',
          isFr ? 'Année 3' : 'Year 3'
        ],
        rows: [
          [isFr ? 'Volume (Unités / Clients)' : 'Volume (Units / Clients)', String(y1.units), String(y2.units), String(y3.units)],
          [
            isFr ? 'Chiffre d’Affaires (Revenus)' : 'Revenue',
            formatCurrency(y1.revenue, plan.currency, doc.language),
            formatCurrency(y2.revenue, plan.currency, doc.language),
            formatCurrency(y3.revenue, plan.currency, doc.language)
          ],
          [
            isFr ? 'Coûts Variables (COGS)' : 'Variable Costs (COGS)',
            formatCurrency(y1.cogs, plan.currency, doc.language),
            formatCurrency(y2.cogs, plan.currency, doc.language),
            formatCurrency(y3.cogs, plan.currency, doc.language)
          ],
          [
            isFr ? 'Marge Brute' : 'Gross Profit',
            `${formatCurrency(y1.grossProfit, plan.currency, doc.language)} (${y1.grossMarginPercent}%)`,
            `${formatCurrency(y2.grossProfit, plan.currency, doc.language)} (${y2.grossMarginPercent}%)`,
            `${formatCurrency(y3.grossProfit, plan.currency, doc.language)} (${y3.grossMarginPercent}%)`
          ],
          [
            isFr ? 'Charges Fixes Annuelles' : 'Annual Fixed Costs',
            formatCurrency(y1.fixedCosts, plan.currency, doc.language),
            formatCurrency(y2.fixedCosts, plan.currency, doc.language),
            formatCurrency(y3.fixedCosts, plan.currency, doc.language)
          ],
          [
            'EBITDA',
            formatCurrency(y1.ebitda, plan.currency, doc.language),
            formatCurrency(y2.ebitda, plan.currency, doc.language),
            formatCurrency(y3.ebitda, plan.currency, doc.language)
          ],
          [
            isFr ? 'Résultat Net' : 'Net Profit',
            formatCurrency(y1.netProfit, plan.currency, doc.language),
            formatCurrency(y2.netProfit, plan.currency, doc.language),
            formatCurrency(y3.netProfit, plan.currency, doc.language)
          ],
          [
            isFr ? 'Trésorerie Cumulée' : 'Cumulative Cash Flow',
            formatCurrency(y1.cumulativeCashFlow, plan.currency, doc.language),
            formatCurrency(y2.cumulativeCashFlow, plan.currency, doc.language),
            formatCurrency(y3.cumulativeCashFlow, plan.currency, doc.language)
          ]
        ],
        type: 'table'
      })
    }
  }

  return blocks
}

/**
 * Convert a BusinessDocument into normalized preview/export blocks consumed by LivePreview and PDF/DOCX builders.
 */
export function serializeBusinessDocument(doc: BusinessDocument): SerializedBlock[] {
  const accentColor = ALL_TEMPLATES.find(t => t.id === doc.templateId)?.accentColor ?? '#0053FD'
  const isFr = doc.language === 'fr'

  switch (doc.type) {
    case 'cv':
      return serializeCv(doc, doc.data as CVData, accentColor, isFr)

    case 'invoice':
    case 'quote':
      return serializeCommercialDoc(doc, accentColor, isFr)

    case 'contract':
      return serializeContract(doc, doc.data as ContractData, accentColor, isFr)

    case 'plan':
      return serializePlan(doc, doc.data as BusinessPlanData, accentColor, isFr)

    case 'deck': {
      const deck = doc.data as PitchDeckData
      const blocks: SerializedBlock[] = [
        {
          accentColor,
          subtitle: `${deck.tagline} · ${deck.presenterName} · ${isFr ? 'Objectif' : 'Target Raise'}: ${formatCurrency(deck.raiseAmount, deck.currency, doc.language)}`,
          title: `${deck.companyName} — ${doc.title}`,
          type: 'header'
        }
      ]

      for (const slide of deck.slides) {
        blocks.push({ level: 1, text: `${slide.title} — ${slide.subtitle}`, type: 'heading' })

        if (slide.metricLabel && slide.metricValue) {
          blocks.push({ kind: 'info', text: `${slide.metricLabel}: ${slide.metricValue}`, type: 'callout' })
        }

        if (slide.bullets.length > 0) {
          blocks.push({ items: slide.bullets, type: 'bullets' })
        }

        if (slide.speakerNotes.trim()) {
          blocks.push({ text: `Notes: ${slide.speakerNotes}`, type: 'paragraph' })
        }
      }

      return blocks
    }

    case 'letter': {
      const letter = doc.data as CoverLetterData
      const blocks: SerializedBlock[] = [
        {
          accentColor,
          subtitle: [letter.senderTitle, letter.senderLocation, letter.senderEmail, letter.senderPhone]
            .filter(Boolean)
            .join(' · '),
          title: letter.senderName || doc.title,
          type: 'header'
        },
        {
          pairs: [
            {
              label: isFr ? 'Destinataire' : 'Recipient',
              value: `${letter.recipientName}, ${letter.recipientTitle} — ${letter.companyName} (${letter.companyAddress})`
            },
            {
              label: isFr ? 'Objet' : 'Subject',
              value: `${isFr ? 'Candidature au poste de' : 'Application for'} ${letter.jobTitle}`
            },
            { label: 'Date', value: formatDocumentDate(letter.date, doc.language) }
          ],
          type: 'keyValueGrid'
        },
        { text: letter.opening, type: 'paragraph' }
      ]

      for (const para of letter.bodyParagraphs) {
        if (para.trim()) {
          blocks.push({ text: para, type: 'paragraph' })
        }
      }

      if (letter.achievements.length > 0) {
        blocks.push(
          { level: 2, text: isFr ? 'Réalisations clés :' : 'Key Achievements:', type: 'heading' },
          { items: letter.achievements.filter(Boolean), type: 'bullets' }
        )
      }

      blocks.push(
        { text: letter.closing, type: 'paragraph' },
        { leftLabel: isFr ? 'Signature' : 'Sincerely', leftName: letter.senderName, type: 'signatures' }
      )

      return blocks
    }

    case 'attestation': {
      const att = doc.data as AttestationData

      return [
        {
          accentColor,
          subtitle: `${att.issuerCompany} · ${att.issuerAddress} · Réf: ${att.referenceNumber}`,
          title: doc.title.toUpperCase(),
          type: 'header'
        },
        {
          pairs: [
            {
              label: isFr ? 'Établissement émetteur' : 'Issuing Organization',
              value: [
                att.issuerCompany,
                att.issuerAddress,
                att.issuerNiu ? `NIU: ${att.issuerNiu}` : '',
                att.issuerRccm ? `RCCM: ${att.issuerRccm}` : ''
              ]
                .filter(Boolean)
                .join(' · ')
            },
            { label: isFr ? 'Bénéficiaire' : 'Recipient', value: att.recipientFullName },
            { label: isFr ? 'Fonction & Département' : 'Role & Department', value: `${att.recipientRole} — ${att.department}` },
            {
              label: isFr ? 'Période' : 'Period',
              value: `${formatDocumentDate(att.startDate, doc.language)} → ${att.isCurrent ? (isFr ? 'En poste à ce jour' : 'Present') : formatDocumentDate(att.endDate, doc.language)}`
            }
          ],
          type: 'keyValueGrid'
        },
        { text: att.bodyText, type: 'paragraph' },
        {
          text: `${isFr ? 'Fait à' : 'Issued in'} ${att.issueCity}, ${isFr ? 'le' : 'on'} ${formatDocumentDate(att.issueDate, doc.language)}.`,
          type: 'paragraph'
        },
        {
          leftLabel: att.signatoryTitle,
          leftName: `${att.signatoryName} (${att.issuerCompany})`,
          type: 'signatures'
        }
      ]
    }

    case 'scan': {
      const scan = doc.data as ScanDocumentData
      const lines = (scan.editedText || scan.rawText || '').split('\n')

      return [
        {
          accentColor,
          subtitle: `${scan.sourceFileName} (${scan.sourceMimeType})`,
          title: doc.title,
          type: 'header'
        },
        { kind: 'info', text: scan.confidenceNote, type: 'callout' },
        ...lines.map((line): ParagraphBlock => ({ text: line || ' ', type: 'paragraph' }))
      ]
    }
  }
}
