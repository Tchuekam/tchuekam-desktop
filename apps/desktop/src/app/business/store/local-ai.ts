import { atom } from 'nanostores'

import type {
  BusinessLocalAiAssistantResult,
  BusinessLocalAiBridge,
  BusinessLocalAiConfig,
  BusinessLocalAiStatus
} from '@/global'
import { IS_DESKTOP } from '@/lib/platform'

import type {
  BusinessDocument,
  BusinessPlanData,
  ContractData,
  CoverLetterData,
  CVData,
  InvoiceData,
  PitchDeckData,
  QuoteData,
  ScanDocumentData
} from '../types'
import {
  analyzeCvAtsReadiness,
  auditContractWarnings,
  calculateBusinessPlanProjections,
  calculateLineItemsSummary,
  formatCurrency
} from '../utils/calculations'

export interface BusinessLocalAiChatMessage {
  content: string
  createdAt: number
  durationMs?: number
  id: string
  role: 'assistant' | 'user'
  tokensPerSec?: number | null
}

export const $businessLocalAiStatus = atom<BusinessLocalAiStatus | null>(null)
export const $businessLocalAiLoading = atom<boolean>(false)
export const $businessLocalAiModalOpen = atom<boolean>(false)
export const $businessLocalAiDrawerOpen = atom<boolean>(false)
export const $businessLocalAiChatBusy = atom<boolean>(false)
export const $businessLocalAiMessages = atom<BusinessLocalAiChatMessage[]>([])

function getDesktopBridge(): BusinessLocalAiBridge | null {
  if (!IS_DESKTOP || typeof window === 'undefined') {
    return null
  }

  return window.hermesDesktop?.businessAi ?? null
}

export async function refreshBusinessLocalAiStatus(): Promise<BusinessLocalAiStatus | null> {
  const bridge = getDesktopBridge()

  if (!bridge) {
    return null
  }

  $businessLocalAiLoading.set(true)

  try {
    const status = await bridge.getStatus()
    $businessLocalAiStatus.set(status)

    return status
  } catch {
    return null
  } finally {
    $businessLocalAiLoading.set(false)
  }
}

export function subscribeBusinessLocalAiStatus(): () => void {
  const bridge = getDesktopBridge()

  if (!bridge) {
    return () => undefined
  }

  void refreshBusinessLocalAiStatus()

  return bridge.onStatus(status => {
    $businessLocalAiStatus.set(status)
  })
}

export async function installBusinessLocalAi(modelId?: string): Promise<BusinessLocalAiStatus> {
  const bridge = getDesktopBridge()

  if (!bridge) {
    throw new Error('Local Business Hub AI is only available in the desktop app.')
  }

  const status = await bridge.install(modelId ? { modelId } : undefined)
  $businessLocalAiStatus.set(status)

  return status
}

export async function cancelBusinessLocalAiInstall(): Promise<void> {
  const bridge = getDesktopBridge()

  if (!bridge) {
    return
  }

  await bridge.cancelInstall()
  await refreshBusinessLocalAiStatus()
}

export async function startBusinessLocalAi(): Promise<void> {
  const bridge = getDesktopBridge()

  if (!bridge) {
    return
  }

  await bridge.start()
  await refreshBusinessLocalAiStatus()
}

export async function unloadBusinessLocalAi(): Promise<void> {
  const bridge = getDesktopBridge()

  if (!bridge) {
    return
  }

  const status = await bridge.unload()
  $businessLocalAiStatus.set(status)
}

export async function updateBusinessLocalAiConfig(
  patch: Partial<BusinessLocalAiConfig>
): Promise<BusinessLocalAiStatus | null> {
  const bridge = getDesktopBridge()

  if (!bridge) {
    return null
  }

  const status = await bridge.setConfig(patch)
  $businessLocalAiStatus.set(status)

  return status
}

export async function deleteBusinessLocalAiModel(modelId: string): Promise<BusinessLocalAiStatus | null> {
  const bridge = getDesktopBridge()

  if (!bridge) {
    return null
  }

  const status = await bridge.deleteModel(modelId)
  $businessLocalAiStatus.set(status)

  return status
}

export function clearBusinessLocalAiMessages(): void {
  $businessLocalAiMessages.set([])
}

export function buildCompactDocumentContext(doc: BusinessDocument | null | undefined): string {
  if (!doc) {
    return ''
  }

  const header = `Type: ${doc.type} | Title: ${doc.title} | Lang: ${doc.language}`
  const toConfirmCount = (JSON.stringify(doc.data).match(/\[to confirm\]/gi) || []).length
  const confirmNote = toConfirmCount > 0 ? ` | Unconfirmed placeholders: ${toConfirmCount}` : ''

  switch (doc.type) {
    case 'cv': {
      const cv = doc.data as CVData
      const ats = analyzeCvAtsReadiness(cv)
      const skills = cv.skills.slice(0, 8).join(', ')

      return `${header} | ATS: ${ats.score}/100${confirmNote}\nName: ${cv.fullName} | Headline: ${cv.headline}\nSkills: ${skills}\nSummary: ${cv.summary.slice(0, 160)}`
    }

    case 'invoice': {
      const inv = doc.data as InvoiceData
      const sum = calculateLineItemsSummary(inv.items, inv.amountPaid)

      return `${header} | Invoice #${inv.invoiceNumber}${confirmNote}\nClient: ${inv.client.companyName || inv.client.name} | Total: ${formatCurrency(sum.grandTotal, inv.currency, doc.language)} | Balance due: ${formatCurrency(sum.balanceDue, inv.currency, doc.language)}`
    }

    case 'quote': {
      const quote = doc.data as QuoteData
      const sum = calculateLineItemsSummary(quote.items, 0)

      return `${header} | Quote #${quote.quoteNumber}${confirmNote}\nClient: ${quote.client.companyName || quote.client.name} | Total: ${formatCurrency(sum.grandTotal, quote.currency, doc.language)} | Status: ${quote.status}`
    }

    case 'contract': {
      const contract = doc.data as ContractData
      const warnings = auditContractWarnings(contract)

      return `${header} | Category: ${contract.category}${confirmNote}\nParties: ${contract.partyAName} & ${contract.partyBName} | Warnings: ${warnings.slice(0, 2).join('; ')}`
    }

    case 'plan': {
      const plan = doc.data as BusinessPlanData
      const proj = calculateBusinessPlanProjections(plan.financialAssumptions)

      return `${header}${confirmNote}\nCompany: ${plan.companyName} | Break-even: ${proj.breakEvenUnitsPerYear} units/yr | Y1 Rev: ${formatCurrency(proj.years[0].revenue, plan.currency, doc.language)}`
    }

    case 'deck': {
      const deck = doc.data as PitchDeckData

      return `${header}${confirmNote}\nCompany: ${deck.companyName} | Raising: ${formatCurrency(deck.raiseAmount, deck.currency, doc.language)} | Slides: ${deck.slides.length}`
    }

    case 'letter': {
      const letter = doc.data as CoverLetterData

      return `${header}${confirmNote}\nTarget Role: ${letter.jobTitle} at ${letter.companyName}\nOpening: ${letter.opening.slice(0, 140)}`
    }

    case 'attestation': {
      return `${header}${confirmNote}`
    }

    case 'scan': {
      const scan = doc.data as ScanDocumentData

      return `${header}\nSource: ${scan.sourceFileName}\nText excerpt: ${scan.editedText.slice(0, 220)}`
    }
  }
}

export function buildDeterministicDocumentAudit(doc: BusinessDocument): string {
  const isFr = doc.language === 'fr'
  const toConfirmCount = (JSON.stringify(doc.data).match(/\[to confirm\]/gi) || []).length
  const lines: string[] = []

  if (doc.type === 'cv') {
    const ats = analyzeCvAtsReadiness(doc.data as CVData)
    const failed = ats.checks.filter(c => !c.passed).map(c => c.label)

    lines.push(
      isFr
        ? `Score ATS actuel : ${ats.score}/100.`
        : `Current ATS score: ${ats.score}/100.`
    )

    if (failed.length > 0) {
      lines.push(
        isFr
          ? `À corriger : ${failed.join(' ; ')}.`
          : `Needs attention: ${failed.join('; ')}.`
      )
    }

    if (ats.missingKeywords.length > 0) {
      lines.push(
        isFr
          ? `Mots-clés manquants : ${ats.missingKeywords.slice(0, 6).join(', ')}.`
          : `Missing job keywords: ${ats.missingKeywords.slice(0, 6).join(', ')}.`
      )
    }
  } else if (doc.type === 'contract') {
    const warnings = auditContractWarnings(doc.data as ContractData)

    lines.push(
      warnings.length > 0
        ? warnings.slice(0, 4).join(' ')
        : isFr
          ? 'Aucun avertissement structurel critique détecté.'
          : 'No critical structural warnings detected.'
    )
  } else if (doc.type === 'invoice' || doc.type === 'quote') {
    const data = doc.data as InvoiceData | QuoteData
    const paid = 'amountPaid' in data ? data.amountPaid : 0
    const sum = calculateLineItemsSummary(data.items, paid)

    lines.push(
      isFr
        ? `Total TTC calculé : ${formatCurrency(sum.grandTotal, data.currency, doc.language)} (TVA : ${formatCurrency(sum.taxTotal, data.currency, doc.language)}).`
        : `Computed Grand Total: ${formatCurrency(sum.grandTotal, data.currency, doc.language)} (Tax: ${formatCurrency(sum.taxTotal, data.currency, doc.language)}).`
    )
  }

  if (toConfirmCount > 0) {
    lines.push(
      isFr
        ? `${toConfirmCount} champ(s) marqués [to confirm] restent à vérifier avant envoi.`
        : `${toConfirmCount} [to confirm] placeholder(s) still require verification before sending.`
    )
  }

  return lines.join('\n')
}

export async function askBusinessLocalAgent(
  message: string,
  doc?: BusinessDocument | null
): Promise<BusinessLocalAiAssistantResult> {
  const trimmed = message.trim()

  if (!trimmed) {
    return { ok: false, error: 'Message is empty.' }
  }

  const userMsg: BusinessLocalAiChatMessage = {
    content: trimmed,
    createdAt: Date.now(),
    id: `biz-user-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    role: 'user'
  }

  $businessLocalAiMessages.set([...$businessLocalAiMessages.get(), userMsg])

  const bridge = getDesktopBridge()

  if (!bridge) {
    const errText = 'Local Business Hub AI is only available in the desktop app.'
    $businessLocalAiMessages.set([
      ...$businessLocalAiMessages.get(),
      {
        content: errText,
        createdAt: Date.now(),
        id: `biz-asst-${Date.now()}`,
        role: 'assistant'
      }
    ])

    return { ok: false, error: errText }
  }

  $businessLocalAiChatBusy.set(true)

  try {
    const history = $businessLocalAiMessages
      .get()
      .slice(-4, -1)
      .map(m => ({ content: m.content, role: m.role }))

    const res = await bridge.askAssistant({
      documentSummary: buildCompactDocumentContext(doc),
      history,
      language: doc?.language ?? 'fr',
      message: trimmed
    })

    if (res.notInstalled) {
      $businessLocalAiModalOpen.set(true)

      const notice =
        'Local Business AI model is not installed yet. Use the installer modal to install the ultra-light 2 GB RAM model.'

      $businessLocalAiMessages.set([
        ...$businessLocalAiMessages.get(),
        {
          content: notice,
          createdAt: Date.now(),
          id: `biz-asst-${Date.now()}`,
          role: 'assistant'
        }
      ])

      return res
    }

    const content =
      res.ok && res.output
        ? res.output
        : res.error || 'Could not generate a response from the local model.'

    $businessLocalAiMessages.set([
      ...$businessLocalAiMessages.get(),
      {
        content,
        createdAt: Date.now(),
        durationMs: res.durationMs,
        id: `biz-asst-${Date.now()}`,
        role: 'assistant',
        tokensPerSec: res.tokensPerSec
      }
    ])

    void refreshBusinessLocalAiStatus()

    return res
  } catch (err) {
    const errMessage = err instanceof Error ? err.message : String(err)
    $businessLocalAiMessages.set([
      ...$businessLocalAiMessages.get(),
      {
        content: `Error: ${errMessage}`,
        createdAt: Date.now(),
        id: `biz-asst-${Date.now()}`,
        role: 'assistant'
      }
    ])

    return { ok: false, error: errMessage }
  } finally {
    $businessLocalAiChatBusy.set(false)
  }
}
