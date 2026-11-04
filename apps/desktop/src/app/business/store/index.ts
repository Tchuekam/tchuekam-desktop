import { atom } from 'nanostores'

import {
  createDefaultDocument,
  DEFAULT_BUSINESS_PROFILE,
  DEFAULT_PERSONAL_PROFILE
} from '../schemas'
import type {
  BusinessDocument,
  BusinessProfile,
  DocumentLanguage,
  DocumentType,
  InvoiceData,
  PersonalProfile,
  QuoteData
} from '../types'
import { generateDocumentNumber } from '../utils/calculations'

const STORAGE_KEYS = {
  businessProfile: 'tchuekam.businessHub.businessProfile.v2',
  documents: 'tchuekam.businessHub.documents.v2',
  locale: 'tchuekam.businessHub.locale.v2',
  personalProfile: 'tchuekam.businessHub.personalProfile.v2'
} as const

function readStorageJson<T>(key: string, fallback: T): T {
  try {
    if (typeof window === 'undefined' || !window.localStorage) {
      return fallback
    }

    const raw = window.localStorage.getItem(key)

    if (!raw) {
      return fallback
    }

    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function writeStorageJson<T>(key: string, value: T): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) {
      return
    }

    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Ignore storage quota errors in restricted environments
  }
}

export const $businessDocuments = atom<BusinessDocument[]>(
  readStorageJson<BusinessDocument[]>(STORAGE_KEYS.documents, [])
)

export const $activeDocumentId = atom<string | null>(null)

export const $businessProfile = atom<BusinessProfile>({
  ...DEFAULT_BUSINESS_PROFILE,
  ...readStorageJson<Partial<BusinessProfile>>(STORAGE_KEYS.businessProfile, {})
})

export const $personalProfile = atom<PersonalProfile>({
  ...DEFAULT_PERSONAL_PROFILE,
  ...readStorageJson<Partial<PersonalProfile>>(STORAGE_KEYS.personalProfile, {})
})

export const $businessLocale = atom<DocumentLanguage>(
  readStorageJson<DocumentLanguage>(STORAGE_KEYS.locale, 'fr')
)

export const $autosaveStatus = atom<'saved' | 'saving'>('saved')

const undoStacks = new Map<string, string[]>()
const redoStacks = new Map<string, string[]>()
const MAX_HISTORY_DEPTH = 30

function persistDocuments(docs: BusinessDocument[]) {
  $businessDocuments.set(docs)
  writeStorageJson(STORAGE_KEYS.documents, docs)
}

export function hydrateBusinessHubFromStorage() {
  const docs = readStorageJson<BusinessDocument[]>(STORAGE_KEYS.documents, [])

  const biz = {
    ...DEFAULT_BUSINESS_PROFILE,
    ...readStorageJson<Partial<BusinessProfile>>(STORAGE_KEYS.businessProfile, {})
  }

  const personal = {
    ...DEFAULT_PERSONAL_PROFILE,
    ...readStorageJson<Partial<PersonalProfile>>(STORAGE_KEYS.personalProfile, {})
  }

  const locale = readStorageJson<DocumentLanguage>(STORAGE_KEYS.locale, 'fr')

  $businessDocuments.set(docs)
  $businessProfile.set(biz)
  $personalProfile.set(personal)
  $businessLocale.set(locale)
}

export function resetBusinessHubStoreForTests() {
  undoStacks.clear()
  redoStacks.clear()
  $activeDocumentId.set(null)
  $businessDocuments.set([])
  $businessProfile.set({ ...DEFAULT_BUSINESS_PROFILE })
  $personalProfile.set({ ...DEFAULT_PERSONAL_PROFILE })
  $businessLocale.set('fr')
  $autosaveStatus.set('saved')
  writeStorageJson(STORAGE_KEYS.documents, [])
  writeStorageJson(STORAGE_KEYS.businessProfile, DEFAULT_BUSINESS_PROFILE)
  writeStorageJson(STORAGE_KEYS.personalProfile, DEFAULT_PERSONAL_PROFILE)
  writeStorageJson(STORAGE_KEYS.locale, 'fr')
}

export function setBusinessLocale(locale: DocumentLanguage) {
  $businessLocale.set(locale)
  writeStorageJson(STORAGE_KEYS.locale, locale)
}

export function saveBusinessProfile(updates: Partial<BusinessProfile>): BusinessProfile {
  const next: BusinessProfile = {
    ...$businessProfile.get(),
    ...updates
  }

  $businessProfile.set(next)
  writeStorageJson(STORAGE_KEYS.businessProfile, next)

  return next
}

export function savePersonalProfile(updates: Partial<PersonalProfile>): PersonalProfile {
  const next: PersonalProfile = {
    ...$personalProfile.get(),
    ...updates
  }

  $personalProfile.set(next)
  writeStorageJson(STORAGE_KEYS.personalProfile, next)

  return next
}

export function createBusinessDocument<T extends DocumentType>(
  type: T,
  options?: {
    initialData?: Partial<BusinessDocument<T>['data']>
    language?: DocumentLanguage
    openImmediately?: boolean
    templateId?: string
    title?: string
  }
): BusinessDocument<T> {
  const existing = $businessDocuments.get()
  const sameTypeCount = existing.filter(d => d.type === type).length
  const language = options?.language ?? $businessLocale.get()

  const doc = createDefaultDocument(
    type,
    language,
    $businessProfile.get(),
    $personalProfile.get(),
    options?.templateId,
    sameTypeCount
  )

  if (options?.title) {
    doc.title = options.title
  }

  if (options?.initialData) {
    doc.data = {
      ...(doc.data as object),
      ...(options.initialData as object)
    } as BusinessDocument<T>['data']
  }

  const nextDocs = [doc, ...existing]
  persistDocuments(nextDocs)

  if (options?.openImmediately !== false) {
    $activeDocumentId.set(doc.id)
  }

  return doc
}

export function openBusinessDocument(id: string | null) {
  $activeDocumentId.set(id)
}

export function getActiveBusinessDocument(): BusinessDocument | null {
  const activeId = $activeDocumentId.get()

  if (!activeId) {
    return null
  }

  return $businessDocuments.get().find(d => d.id === activeId) ?? null
}

export function updateBusinessDocument(
  id: string,
  updater: (current: BusinessDocument) => BusinessDocument,
  recordUndo = true
): BusinessDocument | null {
  const docs = $businessDocuments.get()
  const index = docs.findIndex(d => d.id === id)

  if (index < 0) {
    return null
  }

  const current = docs[index]

  if (!current) {
    return null
  }

  if (recordUndo) {
    const stack = undoStacks.get(id) ?? []
    const serialized = JSON.stringify(current)

    if (stack[stack.length - 1] !== serialized) {
      stack.push(serialized)

      if (stack.length > MAX_HISTORY_DEPTH) {
        stack.shift()
      }

      undoStacks.set(id, stack)
      redoStacks.delete(id)
    }
  }

  const updated = updater(structuredClone(current))

  const nextDoc: BusinessDocument = {
    ...updated,
    id: current.id,
    updatedAt: Date.now()
  }

  $autosaveStatus.set('saving')
  const nextDocs = [...docs]
  nextDocs[index] = nextDoc
  persistDocuments(nextDocs)
  $autosaveStatus.set('saved')

  return nextDoc
}

export function canUndoDocument(id: string): boolean {
  return (undoStacks.get(id)?.length ?? 0) > 0
}

export function canRedoDocument(id: string): boolean {
  return (redoStacks.get(id)?.length ?? 0) > 0
}

export function undoDocumentChange(id: string): BusinessDocument | null {
  const stack = undoStacks.get(id)

  if (!stack || stack.length === 0) {
    return null
  }

  const docs = $businessDocuments.get()
  const index = docs.findIndex(d => d.id === id)

  if (index < 0 || !docs[index]) {
    return null
  }

  const current = docs[index]
  const previousJson = stack.pop()

  if (!previousJson) {
    return null
  }

  const rStack = redoStacks.get(id) ?? []
  rStack.push(JSON.stringify(current))
  redoStacks.set(id, rStack)

  const restored = JSON.parse(previousJson) as BusinessDocument
  restored.updatedAt = Date.now()

  const nextDocs = [...docs]
  nextDocs[index] = restored
  persistDocuments(nextDocs)

  return restored
}

export function redoDocumentChange(id: string): BusinessDocument | null {
  const rStack = redoStacks.get(id)

  if (!rStack || rStack.length === 0) {
    return null
  }

  const docs = $businessDocuments.get()
  const index = docs.findIndex(d => d.id === id)

  if (index < 0 || !docs[index]) {
    return null
  }

  const current = docs[index]
  const nextJson = rStack.pop()

  if (!nextJson) {
    return null
  }

  const uStack = undoStacks.get(id) ?? []
  uStack.push(JSON.stringify(current))
  undoStacks.set(id, uStack)

  const restored = JSON.parse(nextJson) as BusinessDocument
  restored.updatedAt = Date.now()

  const nextDocs = [...docs]
  nextDocs[index] = restored
  persistDocuments(nextDocs)

  return restored
}

export function duplicateBusinessDocument(id: string): BusinessDocument | null {
  const docs = $businessDocuments.get()
  const target = docs.find(d => d.id === id)

  if (!target) {
    return null
  }

  const now = Date.now()
  const copySuffix = target.language === 'fr' ? ' (Copie)' : ' (Copy)'

  const cloned: BusinessDocument = {
    ...structuredClone(target),
    createdAt: now,
    id: `doc-${target.type}-${now}-${Math.random().toString(36).slice(2, 7)}`,
    status: 'draft',
    title: `${target.title}${copySuffix}`,
    updatedAt: now
  }

  persistDocuments([cloned, ...docs])

  return cloned
}

export function renameBusinessDocument(id: string, title: string): BusinessDocument | null {
  const trimmed = title.trim()

  if (!trimmed) {
    return null
  }

  return updateBusinessDocument(id, doc => ({
    ...doc,
    title: trimmed
  }))
}

export function deleteBusinessDocument(id: string): void {
  const docs = $businessDocuments.get()
  const filtered = docs.filter(d => d.id !== id)
  undoStacks.delete(id)
  redoStacks.delete(id)
  persistDocuments(filtered)

  if ($activeDocumentId.get() === id) {
    $activeDocumentId.set(null)
  }
}

export function convertQuoteToInvoice(quoteDocId: string): BusinessDocument<'invoice'> | null {
  const docs = $businessDocuments.get()

  const quoteDoc = docs.find(d => d.id === quoteDocId && d.type === 'quote') as
    | BusinessDocument<'quote'>
    | undefined

  if (!quoteDoc) {
    return null
  }

  const quoteData = quoteDoc.data as QuoteData
  const invoiceCount = docs.filter(d => d.type === 'invoice').length

  const selectedItems = quoteData.items
    .filter(item => (item.optional ? Boolean(item.selected) : true))
    .map(item => ({
      ...structuredClone(item),
      optional: false,
      selected: true
    }))

  const today = new Date().toISOString().slice(0, 10)
  const dueDate = new Date(Date.now() + 14 * 86_400_000).toISOString().slice(0, 10)

  const invoiceData: InvoiceData = {
    amountPaid: 0,
    client: structuredClone(quoteData.client),
    currency: quoteData.currency,
    description: quoteData.description,
    dueDate,
    invoiceNumber: generateDocumentNumber('INV', invoiceCount),
    issueDate: today,
    items: selectedItems,
    notes: quoteData.notes,
    paymentDetails: quoteData.paymentDetails,
    paymentMethod: quoteData.paymentMethod,
    paymentStatus: 'unpaid',
    paymentTerms: quoteData.paymentTerms,
    seller: structuredClone(quoteData.seller),
    signatoryName: quoteData.signatoryName
  }

  const newInvoice = createBusinessDocument('invoice', {
    initialData: invoiceData,
    language: quoteDoc.language,
    openImmediately: true,
    title:
      quoteDoc.language === 'fr'
        ? `Facture (${quoteData.quoteNumber})`
        : `Invoice (${quoteData.quoteNumber})`
  })

  updateBusinessDocument(
    quoteDocId,
    doc => ({
      ...doc,
      data: {
        ...(doc.data as QuoteData),
        convertedInvoiceId: newInvoice.id,
        status: 'accepted'
      },
      status: 'final'
    }),
    false
  )

  return newInvoice
}
