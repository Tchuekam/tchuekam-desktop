import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { $terminalTakeover } from '@/app/right-sidebar/store'
import { Codicon } from '@/components/ui/codicon'
import { IS_DESKTOP } from '@/lib/platform'
import { cn } from '@/lib/utils'
import { notify } from '@/store/notifications'

import { exportBusinessDocument } from '../../exporters'
import { BUILDER_PROMPTS } from '../../prompts'
import { ALL_TEMPLATES, CV_TEMPLATES, SUPPORTED_EXPORT_FORMATS, validateDocument } from '../../schemas'
import {
  type BusinessAiOperation,
  extractDocumentFromFile,
  runDocumentAiOperation
} from '../../services/ai-orchestrator'
import {
  $autosaveStatus,
  canRedoDocument,
  canUndoDocument,
  convertQuoteToInvoice,
  duplicateBusinessDocument,
  openBusinessDocument,
  redoDocumentChange,
  undoDocumentChange,
  updateBusinessDocument
} from '../../store'
import {
  $businessLocalAiDrawerOpen,
  subscribeBusinessLocalAiStatus
} from '../../store/local-ai'
import type {
  AttestationData,
  BusinessDocument,
  BusinessPlanData,
  ContractData,
  CoverLetterData,
  CVData,
  DocumentDataMap,
  DocumentLanguage,
  DocumentType,
  ExportFormat,
  InvoiceData,
  PitchDeckData,
  QuoteData,
  ScanDocumentData
} from '../../types'
import {
  BusinessLocalAiModal,
  BusinessLocalAiStatusBadge,
  BusinessLocalAiWorkspaceDrawer
} from '../local-ai/business-local-agent-panel'
import { DocumentPreview } from '../preview/document-preview'

import { DocumentForms } from './document-forms'

export interface DocumentWorkspaceProps {
  document: BusinessDocument
  onBack: () => void
  onOpenChat: (prompt: string) => void
}

export function DocumentWorkspace({
  document: doc,
  onBack,
  onOpenChat
}: DocumentWorkspaceProps) {
  const takeover = useStore($terminalTakeover)
  const autosave = useStore($autosaveStatus)
  const [activeSlideIndex, setActiveSlideIndex] = useState(0)
  const [aiBusy, setAiBusy] = useState<string | null>(null)
  const [lastExportInfo, setLastExportInfo] = useState<string | null>(null)
  const [mobilePane, setMobilePane] = useState<'editor' | 'preview'>('editor')

  const canUseAi = !takeover
  const supportedFormats = SUPPORTED_EXPORT_FORMATS[doc.type] ?? ['pdf', 'docx']

  const availableTemplates =
    doc.type === 'cv'
      ? Object.values(CV_TEMPLATES)
      : ALL_TEMPLATES.filter(t => t.documentType === doc.type)

  const validation = validateDocument(doc)

  // Global Keyboard Shortcuts for Undo & Redo (Cmd+Z / Ctrl+Z, Cmd+Shift+Z / Ctrl+Y)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept when user is typing in an input/textarea with native undo
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
      const isInput = tag === 'input' || tag === 'textarea' || (e.target as HTMLElement)?.isContentEditable

      const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform)
      const mod = isMac ? e.metaKey : e.ctrlKey

      if (!mod) {
        return
      }

      if (e.key === 'z' || e.key === 'Z') {
        if (e.shiftKey) {
          // Redo
          if (!isInput && canRedoDocument(doc.id)) {
            e.preventDefault()
            redoDocumentChange(doc.id)
          }
        } else {
          // Undo
          if (!isInput && canUndoDocument(doc.id)) {
            e.preventDefault()
            undoDocumentChange(doc.id)
          }
        }
      } else if (e.key === 'y' || e.key === 'Y') {
        // Redo (Ctrl+Y on Windows/Linux)
        if (!isInput && canRedoDocument(doc.id)) {
          e.preventDefault()
          redoDocumentChange(doc.id)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [doc.id])

  const handleUpdateData = <T extends DocumentType>(
    updater: (current: DocumentDataMap[T]) => DocumentDataMap[T]
  ) => {
    updateBusinessDocument(doc.id, current => ({
      ...current,
      data: updater(current.data as DocumentDataMap[T])
    }))
  }

  const handleRunAi = (
    operation: BusinessAiOperation,
    input: string,
    context: string,
    apply: (output: string, suggestions?: string[]) => void
  ) => {
    if (!canUseAi) {
      return
    }

    setAiBusy(operation)
    void runDocumentAiOperation({
      context,
      input,
      language: doc.language,
      operation
    })
      .then(res => {
        apply(res.output, res.suggestions)
        notify({
          kind: 'success',
          message: 'AI grounded enhancement applied.',
          title: 'AI Assistant'
        })
      })
      .catch((err: unknown) => {
        notify({
          kind: 'error',
          message: err instanceof Error ? err.message : 'AI operation failed.',
          title: 'AI Error'
        })
      })
      .finally(() => setAiBusy(null))
  }

  const handleTranslateDocument = () => {
    const nextLang: DocumentLanguage = doc.language === 'fr' ? 'en' : 'fr'

    if (doc.type === 'cv') {
      const cv = doc.data as CVData
      handleRunAi('translate', cv.summary, cv.headline, translatedSummary => {
        updateBusinessDocument(doc.id, current => ({
          ...current,
          data: {
            ...(current.data as CVData),
            summary: translatedSummary
          },
          language: nextLang
        }))
      })
    } else {
      updateBusinessDocument(doc.id, current => ({
        ...current,
        language: nextLang
      }))
    }
  }

  const handleExport = (format: ExportFormat) => {
    try {
      const res = exportBusinessDocument(doc, format)
      const kb = Math.max(1, Math.round(res.bytes.byteLength / 1024))
      const msg = `Exported ${res.filename} (${kb} KB)`
      setLastExportInfo(msg)
      notify({
        kind: 'success',
        message: msg,
        title: `Export ${format.toUpperCase()} Complete`
      })
    } catch (err: unknown) {
      notify({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Export failed.',
        title: 'Export Error'
      })
    }
  }

  const handleReplaceScanFile = (file: File) => {
    void extractDocumentFromFile(file)
      .then(res => {
        handleUpdateData<'scan'>(current => ({
          ...current,
          editedText: res.extractedText,
          extractedAt: Date.now(),
          rawText: res.extractedText,
          sourceFileName: res.fileName,
          sourceMimeType: res.mimeType
        }))
      })
      .catch((err: unknown) => {
        notify({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Could not scan file.',
          title: 'Scan Error'
        })
      })
  }

  const handleConvertQuote = (quoteId: string) => {
    const created = convertQuoteToInvoice(quoteId)

    if (created) {
      notify({
        kind: 'success',
        message: `Created ${created.title} from quotation.`,
        title: 'Converted to Invoice'
      })
    }
  }

  const handleDuplicate = () => {
    const copy = duplicateBusinessDocument(doc.id)

    if (copy) {
      openBusinessDocument(copy.id)
      notify({
        kind: 'success',
        message: `Created ${copy.title}.`,
        title: 'Document Duplicated'
      })
    }
  }

  const drawerOpen = useStore($businessLocalAiDrawerOpen)

  useEffect(() => {
    if (!IS_DESKTOP) {
      return
    }

    return subscribeBusinessLocalAiStatus()
  }, [])

  const handleApplyLocalAiText = (text: string) => {
    const cleaned = text.trim()

    if (!cleaned) {
      return
    }

    switch (doc.type) {
      case 'cv':
        handleUpdateData<'cv'>(c => ({ ...(c as CVData), summary: cleaned }))

        break

      case 'letter':
        handleUpdateData<'letter'>(c => ({
          ...(c as CoverLetterData),
          bodyParagraphs: cleaned.split(/\n\n+/).filter(Boolean)
        }))

        break

      case 'attestation':
        handleUpdateData<'attestation'>(c => ({ ...(c as AttestationData), bodyText: cleaned }))

        break

      case 'contract':
        handleUpdateData<'contract'>(c => ({ ...(c as ContractData), scope: cleaned }))

        break

      case 'invoice':
        handleUpdateData<'invoice'>(c => ({ ...(c as InvoiceData), notes: cleaned }))

        break

      case 'quote':
        handleUpdateData<'quote'>(c => ({ ...(c as QuoteData), notes: cleaned }))

        break

      case 'plan':
        handleUpdateData<'plan'>(c => {
