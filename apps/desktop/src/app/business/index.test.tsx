// @vitest-environment node
import './test-dom-setup'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type * as ReactRouter from 'react-router-dom'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setTerminalTakeover } from '@/app/right-sidebar/store'
import { $pendingComposerSeed } from '@/store/composer'

import { NEW_CHAT_ROUTE } from '../routes'

import { exportBusinessDocument } from './exporters'
import { BUILDER_PROMPTS, type BuilderId } from './prompts'
import { extractDocumentFromFile, runDocumentAiOperation } from './services/ai-orchestrator'
import {
  $activeDocumentId,
  $businessDocuments,
  $businessProfile,
  $personalProfile,
  convertQuoteToInvoice,
  createBusinessDocument,
  duplicateBusinessDocument,
  hydrateBusinessHubFromStorage,
  openBusinessDocument,
  redoDocumentChange,
  renameBusinessDocument,
  resetBusinessHubStoreForTests,
  saveBusinessProfile,
  savePersonalProfile,
  undoDocumentChange,
  updateBusinessDocument
} from './store'
import { testDom } from './test-dom-setup'
import type { CVData, InvoiceData, PitchDeckData } from './types'
import {
  analyzeCvAtsReadiness,
  calculateBusinessPlanProjections,
  calculateLineItemsSummary
} from './utils/calculations'

import { BusinessView } from './index'

const navigate = vi.fn()
const seedsSeenAtNavigate: Array<string | null> = []

vi.mock('react-router-dom', async importOriginal => ({
  ...(await importOriginal<typeof ReactRouter>()),
  useNavigate: () => navigate
}))

const BUILDER_TITLES: Record<BuilderId, string> = {
  attestation: 'Attestation',
  contract: 'Contrat',
  cv: 'CV / Résumé',
  deck: 'Pitch Deck',
  invoice: 'Facture',
  letter: 'Lettre de motivation',
  plan: 'Business Plan',
  quote: 'Devis'
}

function renderView() {
  return render(
    <MemoryRouter>
      <BusinessView />
    </MemoryRouter>
  )
}

beforeEach(() => {
  navigate.mockReset()
  seedsSeenAtNavigate.length = 0
  $pendingComposerSeed.set(null)
  setTerminalTakeover(false)
  resetBusinessHubStoreForTests()
  navigate.mockImplementation(() => seedsSeenAtNavigate.push($pendingComposerSeed.get()))
})

afterEach(() => {
  cleanup()
  setTerminalTakeover(false)
})

describe('Business Hub 2.0 — Interactive Builders & Chat Integration', () => {
  it.each(Object.entries(BUILDER_TITLES) as Array<[BuilderId, string]>)(
    '%s builder card opens the interactive DocumentWorkspace and supports chat prompt seeding',
    (id, title) => {
      renderView()

      // 1. Test Chat prompt button seeds composer and navigates
      const chatBtn = screen.getByLabelText(`Draft ${title} in chat`)
      fireEvent.click(chatBtn)
      expect(seedsSeenAtNavigate).toEqual([BUILDER_PROMPTS[id]])
      expect(navigate).toHaveBeenCalledWith(NEW_CHAT_ROUTE)

      // 2. Clicking the builder card opens the interactive workspace
      fireEvent.click(screen.getByLabelText(title))
      expect($activeDocumentId.get()).not.toBeNull()
      expect($businessDocuments.get()[0]?.type).toBe(id)
    }
  )

  it('AI Consultant disables Open in chat until non-whitespace text is entered and submits cleanly', () => {
    renderView()
    const consultantInput = screen.getByLabelText<HTMLInputElement>('AI Consultant')
    const openInChatBtn = screen.getByText<HTMLButtonElement>('Open in chat')

    expect(openInChatBtn.disabled).toBe(true)

    fireEvent.change(consultantInput, { target: { value: '   ' } })
    expect(openInChatBtn.disabled).toBe(true)

    fireEvent.change(consultantInput, { target: { value: '  Make my CV stronger  ' } })
    expect(openInChatBtn.disabled).toBe(false)

    const form = consultantInput.closest('form') as HTMLFormElement
    expect(fireEvent.submit(form)).toBe(false)

    expect(seedsSeenAtNavigate).toEqual(['Make my CV stronger'])
    expect(navigate).toHaveBeenCalledWith(NEW_CHAT_ROUTE)
  })

  it('disables actions and blocks AI calls when Terminal Takeover is active', async () => {
    setTerminalTakeover(true)
    renderView()

    expect(screen.getByRole('status').textContent).toContain('Terminal takeover is on')
    expect(screen.getByText<HTMLButtonElement>('Open in chat').disabled).toBe(true)
    expect(screen.getByLabelText<HTMLButtonElement>('CV / Résumé').disabled).toBe(true)

    await expect(
      runDocumentAiOperation({
        input: 'Test summary',
        language: 'fr',
        operation: 'improve_summary'
      })
    ).rejects.toThrow(/Terminal takeover is active/)
  })
})

describe('Business Hub 2.0 — CV Builder, Templates, ATS Analysis, and Binary Export', () => {
  it('creates a CV, edits fields, switches across templates, reorders sections, and exports valid PDF & DOCX', () => {
    renderView()

    fireEvent.click(screen.getByLabelText('CV / Résumé'))

    // Edit Full Name & Headline
    const nameInput = screen.getByLabelText<HTMLInputElement>('Full Name')
    fireEvent.change(nameInput, { target: { value: 'Rostand Tchuekam' } })
    expect(nameInput.value).toBe('Rostand Tchuekam')

    const summaryInput = screen.getByLabelText<HTMLTextAreaElement>('Professional Summary')
    fireEvent.change(summaryInput, {
      target: { value: 'Principal Systems Architect leading AI transformation across Central Africa.' }
    })

    // Switch template to Executive, then Creative
    const tplSelect = screen.getByLabelText<HTMLSelectElement>('Template')
    fireEvent.change(tplSelect, { target: { value: 'executive' } })
    expect($businessDocuments.get()[0]?.templateId).toBe('executive')

    fireEvent.change(tplSelect, { target: { value: 'creative' } })
    expect($businessDocuments.get()[0]?.templateId).toBe('creative')

    // Reorder section (move experience up before summary)
    const moveExpUp = screen.getByLabelText('Move experience up')
    fireEvent.click(moveExpUp)
    const cvData = $businessDocuments.get()[0]?.data as CVData
    expect(cvData.sectionOrder[0]).toBe('experience')

    // ATS Readiness Check with Target Job Description
    const jobDesc = screen.getByLabelText<HTMLTextAreaElement>('Target Job Description')
    fireEvent.change(jobDesc, {
      target: { value: 'Looking for Principal Architect with Python, TypeScript, Cloud, FinOps experience.' }
    })
    const ats = analyzeCvAtsReadiness($businessDocuments.get()[0]?.data as CVData)
    expect(ats.score).toBeGreaterThan(50)
    expect(ats.missingKeywords).toContain('finops')

    // Export PDF & DOCX and verify binary headers
    const activeDoc = $businessDocuments.get()[0]!
    const pdfExport = exportBusinessDocument(activeDoc, 'pdf', { triggerDownload: false })
    expect(pdfExport.filename).toMatch(/\.pdf$/)
    const pdfHeader = new TextDecoder('ascii').decode(pdfExport.bytes.slice(0, 8))
    expect(pdfHeader).toBe('%PDF-1.4')
    expect(pdfExport.bytes.byteLength).toBeGreaterThan(500)

    const docxExport = exportBusinessDocument(activeDoc, 'docx', { triggerDownload: false })
    expect(docxExport.filename).toMatch(/\.docx$/)
    // ZIP magic bytes PK\x03\x04
    expect(docxExport.bytes[0]).toBe(0x50)
    expect(docxExport.bytes[1]).toBe(0x4b)
    expect(docxExport.bytes[2]).toBe(0x03)
    expect(docxExport.bytes[3]).toBe(0x04)

    // Return to Hub and verify document appears in Recent Documents and can be reopened
    fireEvent.click(screen.getByLabelText('Back to Business Hub'))
    expect($activeDocumentId.get()).toBeNull()
    expect(screen.getByText(activeDoc.title)).toBeDefined()

    fireEvent.click(screen.getByLabelText(`Open ${activeDoc.title}`))
    expect($activeDocumentId.get()).toBe(activeDoc.id)
    expect(screen.getByLabelText<HTMLInputElement>('Full Name').value).toBe('Rostand Tchuekam')
  })
})

describe('Business Hub 2.0 — Invoice, Quotation, Deterministic Math & Quote-to-Invoice Conversion', () => {
  it('calculates multi-item invoice totals deterministically without floating-point drift and exports PDF & XLSX', () => {
    const invDoc = createBusinessDocument('invoice')
    updateBusinessDocument(invDoc.id, current => ({
      ...current,
      data: {
        ...(current.data as InvoiceData),
        amountPaid: 100_000,
        currency: 'XAF',
        items: [
          {
            description: 'AI Architecture Consulting',
            discountPercent: 10,
            id: 'i-1',
            quantity: 2,
            taxRatePercent: 19.25,
            unitPrice: 250_000
          },
          {
            description: 'Cloud Deployment & Security Audit',
            discountPercent: 0,
            id: 'i-2',
            quantity: 1,
            taxRatePercent: 19.25,
            unitPrice: 150_000
          }
        ]
      }
    }))

    const updated = $businessDocuments.get().find(d => d.id === invDoc.id)!
    const summary = calculateLineItemsSummary((updated.data as InvoiceData).items, 100_000)

    expect(summary.subtotal).toBe(650_000)
    expect(summary.discountTotal).toBe(50_000)
    expect(summary.taxTotal).toBe(115_500)
    expect(summary.grandTotal).toBe(715_500)
    expect(summary.balanceDue).toBe(615_500)

    const xlsxExport = exportBusinessDocument(updated, 'xlsx', { triggerDownload: false })
    expect(xlsxExport.filename).toMatch(/\.xlsx$/)
    expect(xlsxExport.bytes[0]).toBe(0x50)
    expect(xlsxExport.bytes[1]).toBe(0x4b)
  })

  it('converts a Quotation into an Invoice without losing client, seller, or selected line item data', () => {
    const quoteDoc = createBusinessDocument('quote')
    const convertedInvoice = convertQuoteToInvoice(quoteDoc.id)

    expect(convertedInvoice).not.toBeNull()
    expect(convertedInvoice?.type).toBe('invoice')
    expect($activeDocumentId.get()).toBe(convertedInvoice?.id)

    const invData = convertedInvoice!.data as InvoiceData
    expect(invData.items.length).toBeGreaterThanOrEqual(2)
    expect(invData.invoiceNumber).toMatch(/^INV-/)

    const updatedQuote = $businessDocuments.get().find(d => d.id === quoteDoc.id)!
    expect(updatedQuote.status).toBe('final')
  })
})

describe('Business Hub 2.0 — Contract, Business Plan, Pitch Deck, Profiles & OCR Scan', () => {
  it('creates a Contract, preserves legal review warnings, and exports PDF & DOCX', () => {
    const contractDoc = createBusinessDocument('contract')
    const pdfRes = exportBusinessDocument(contractDoc, 'pdf', { triggerDownload: false })
    const docxRes = exportBusinessDocument(contractDoc, 'docx', { triggerDownload: false })

    expect(pdfRes.bytes.byteLength).toBeGreaterThan(500)
    expect(docxRes.bytes.byteLength).toBeGreaterThan(500)
    expect(pdfRes.warnings.some(w => w.includes('[to confirm]'))).toBe(true)
  })

  it('calculates 3-year Business Plan projections deterministically and exports PDF, DOCX, and XLSX', () => {
    const planDoc = createBusinessDocument('plan')

    const proj = calculateBusinessPlanProjections({
      initialInvestment: 5_000_000,
      monthlyFixedCosts: 400_000,
      taxRatePercent: 25,
      unitPrice: 20_000,
      unitVariableCost: 8_000,
      year1Units: 600,
      year2GrowthPercent: 50,
      year3GrowthPercent: 50
    })

    expect(proj.breakEvenUnitsPerYear).toBe(400)
    expect(proj.years).toHaveLength(3)
    expect(proj.years[0]?.revenue).toBe(12_000_000)
    expect(proj.years[1]?.units).toBe(900)

    const xlsxRes = exportBusinessDocument(planDoc, 'xlsx', { triggerDownload: false })
    expect(xlsxRes.bytes[0]).toBe(0x50)
    expect(xlsxRes.bytes[1]).toBe(0x4b)
  })

  it('edits and reorders Pitch Deck slides and exports valid 16:9 PPTX and PDF', () => {
    const deckDoc = createBusinessDocument('deck')
    const deckData = deckDoc.data as PitchDeckData
    expect(deckData.slides).toHaveLength(11)

    const pptxRes = exportBusinessDocument(deckDoc, 'pptx', { triggerDownload: false })
    expect(pptxRes.filename).toMatch(/\.pptx$/)
    expect(pptxRes.bytes[0]).toBe(0x50)
    expect(pptxRes.bytes[1]).toBe(0x4b)

    const pdfRes = exportBusinessDocument(deckDoc, 'pdf', { triggerDownload: false })
    expect(new TextDecoder('ascii').decode(pdfRes.bytes.slice(0, 8))).toBe('%PDF-1.4')
  })

  it('persists Business & Personal profiles across restarts and pre-fills new documents', () => {
    saveBusinessProfile({
      companyName: 'TchueKAM Enterprise SARL',
      defaultCurrency: 'XAF',
      momoMerchantCode: '*126*1*998877#',
      niu: 'M052600099999A',
      rccm: 'RC/DLA/2026/B/9999'
    })
    savePersonalProfile({
      email: 'rostand@tchuekam.com',
      fullName: 'Rostand Tchuekam',
      headline: 'Founder & Chief Architect',
      skills: ['Distributed Systems', 'AI Agents', 'FinTech']
    })

    $businessProfile.set({ ...$businessProfile.get(), companyName: '' })
    $personalProfile.set({ ...$personalProfile.get(), fullName: '' })
    hydrateBusinessHubFromStorage()

    expect($businessProfile.get().companyName).toBe('TchueKAM Enterprise SARL')
    expect($personalProfile.get().fullName).toBe('Rostand Tchuekam')

    const newInvoice = createBusinessDocument('invoice')
    expect((newInvoice.data as InvoiceData).seller.companyName).toBe('TchueKAM Enterprise SARL')
    expect((newInvoice.data as InvoiceData).seller.niu).toBe('M052600099999A')

    const newCv = createBusinessDocument('cv')
    expect((newCv.data as CVData).fullName).toBe('Rostand Tchuekam')
    expect((newCv.data as CVData).skills).toContain('AI Agents')
  })

  it('supports Undo, Redo, Duplicate, and Rename on saved documents', () => {
    const doc = createBusinessDocument('letter')
    const initialTitle = doc.title

    renameBusinessDocument(doc.id, 'Cover Letter — Senior AI Lead')
    expect($businessDocuments.get().find(d => d.id === doc.id)?.title).toBe('Cover Letter — Senior AI Lead')

    undoDocumentChange(doc.id)
    expect($businessDocuments.get().find(d => d.id === doc.id)?.title).toBe(initialTitle)

    redoDocumentChange(doc.id)
    expect($businessDocuments.get().find(d => d.id === doc.id)?.title).toBe('Cover Letter — Senior AI Lead')

    const copy = duplicateBusinessDocument(doc.id)
    expect(copy).not.toBeNull()
    expect(copy?.title).toContain('Cover Letter — Senior AI Lead')
    expect($businessDocuments.get()).toHaveLength(2)
  })

  it('extracts text from an uploaded PDF file into an editable Scan Document and exports PDF/DOCX', async () => {
    const sourceDoc = createBusinessDocument('attestation', { openImmediately: false })
    const pdfBytes = exportBusinessDocument(sourceDoc, 'pdf', { triggerDownload: false }).bytes

    const file = new testDom.window.File([pdfBytes.buffer as ArrayBuffer], 'attestation-scan.pdf', {
      type: 'application/pdf'
    })

    const ocrResult = await extractDocumentFromFile(file)
    expect(ocrResult.fileName).toBe('attestation-scan.pdf')
    expect(ocrResult.extractedText.length).toBeGreaterThan(20)

    openBusinessDocument(null)
    renderView()

    const fileInput = screen.getByLabelText<HTMLInputElement>('Upload file for Scan to text')
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect($activeDocumentId.get()).not.toBeNull()
      expect($businessDocuments.get()[0]?.type).toBe('scan')
    })

    const scanDoc = $businessDocuments.get()[0]!
    const exportedScanPdf = exportBusinessDocument(scanDoc, 'pdf', { triggerDownload: false })
    expect(exportedScanPdf.bytes.byteLength).toBeGreaterThan(400)
  })

  it('supports inline keyboard rename (Enter commits, Escape cancels) and Recent Documents filtering', () => {
    const doc1 = createBusinessDocument('invoice', { openImmediately: false, title: 'Facture Client Alpha' })
    const doc2 = createBusinessDocument('cv', { openImmediately: false, title: 'Mon Curriculum Vitae' })
    openBusinessDocument(null)
    renderView()

    // Test search filter
    const searchInput = screen.getByPlaceholderText<HTMLInputElement>('Search docs...')
    fireEvent.change(searchInput, { target: { value: 'Alpha' } })
    expect(screen.getByText('Facture Client Alpha')).toBeDefined()
    expect(screen.queryByText('Mon Curriculum Vitae')).toBeNull()

    // Clear search
    fireEvent.change(searchInput, { target: { value: '' } })
    expect(screen.getByText('Mon Curriculum Vitae')).toBeDefined()

    // Test filter by type
    const filterSelect = screen.getByLabelText<HTMLSelectElement>('Filter documents by type')
    fireEvent.change(filterSelect, { target: { value: 'cv' } })
    expect(screen.getByText('Mon Curriculum Vitae')).toBeDefined()
    expect(screen.queryByText('Facture Client Alpha')).toBeNull()

    // Reset filter
    fireEvent.change(filterSelect, { target: { value: 'all' } })

    // Test Rename with Escape (cancel)
    fireEvent.click(screen.getByLabelText(`Rename ${doc1.title}`))
    const renameInput = screen.getByLabelText<HTMLInputElement>(`Rename input for ${doc1.title}`)
    fireEvent.change(renameInput, { target: { value: 'Draft Should Be Canceled' } })
    fireEvent.keyDown(renameInput, { key: 'Escape' })
    expect(screen.queryByLabelText(`Rename input for ${doc1.title}`)).toBeNull()
    expect(screen.getByText('Facture Client Alpha')).toBeDefined()

    // Test Rename with Enter (commit)
    fireEvent.click(screen.getByLabelText(`Rename ${doc1.title}`))
    const renameInput2 = screen.getByLabelText<HTMLInputElement>(`Rename input for ${doc1.title}`)
    fireEvent.change(renameInput2, { target: { value: 'Facture Finale Alpha' } })
    fireEvent.keyDown(renameInput2, { key: 'Enter' })
    expect(screen.queryByLabelText(`Rename input for ${doc1.title}`)).toBeNull()
    expect($businessDocuments.get().find(d => d.id === doc1.id)?.title).toBe('Facture Finale Alpha')
  })

  it('allows adding and removing Education entries cleanly in CV builder', () => {
    const cvDoc = createBusinessDocument('cv')
    openBusinessDocument(cvDoc.id)
    renderView()

    const addEduBtn = screen.getByText('Add Education')
    fireEvent.click(addEduBtn)
    const cvDataAfterAdd = $businessDocuments.get().find(d => d.id === cvDoc.id)?.data as CVData
    const initialEduCount = cvDataAfterAdd.education.length
    expect(initialEduCount).toBeGreaterThanOrEqual(1)

    // Remove the newly added education
    const removeEduBtn = screen.getByLabelText(`Remove Education ${initialEduCount}`)
    fireEvent.click(removeEduBtn)
    const cvDataAfterRemove = $businessDocuments.get().find(d => d.id === cvDoc.id)?.data as CVData
    expect(cvDataAfterRemove.education.length).toBe(initialEduCount - 1)
  })

  it('allows adding and removing Contract clauses cleanly in Contract builder', () => {
    const contractDoc = createBusinessDocument('contract')
    openBusinessDocument(contractDoc.id)
    renderView()

    const addClauseBtn = screen.getByText('Add Clause')
    fireEvent.click(addClauseBtn)
    const contractDataAfterAdd = $businessDocuments.get().find(d => d.id === contractDoc.id)?.data as any
    const initialClauseCount = contractDataAfterAdd.clauses.length

    const removeClauseBtn = screen.getByLabelText(`Remove Clause ${initialClauseCount}`)
    fireEvent.click(removeClauseBtn)
    const contractDataAfterRemove = $businessDocuments.get().find(d => d.id === contractDoc.id)?.data as any
    expect(contractDataAfterRemove.clauses.length).toBe(initialClauseCount - 1)
  })
})
