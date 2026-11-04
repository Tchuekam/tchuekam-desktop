import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { $terminalTakeover } from '@/app/right-sidebar/store'
import { Codicon } from '@/components/ui/codicon'
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
import type {
  BusinessDocument,
  CVData,
  DocumentDataMap,
  DocumentLanguage,
  DocumentType,
  ExportFormat
} from '../../types'
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

  const handleAskInChat = () => {
    const basePrompt =
      doc.type === 'scan'
        ? `Review this extracted text from "${doc.title}":\n\n`
        : BUILDER_PROMPTS[doc.type]

    onOpenChat(`${basePrompt}\n\nDocument title: ${doc.title}`)
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background text-foreground pt-(--titlebar-height)">
      {/* Apple-style Studio Navigation & Command Bar */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 bg-card/85 px-6 py-3 shadow-xs backdrop-blur-md">
        <div className="flex items-center gap-3">
          <button
            aria-label="Back to Business Hub"
            className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-border/70 bg-background/80 px-3 text-xs font-semibold text-muted-foreground transition hover:border-primary/40 hover:bg-muted hover:text-foreground"
            onClick={onBack}
            type="button"
          >
            <Codicon name="arrow-left" size="0.85rem" />
            <span>Hub</span>
          </button>

          <div className="relative flex items-center">
            <input
              aria-label="Document Title"
              className="h-8 min-w-[220px] rounded-xl border border-border/70 bg-background/80 px-3 text-xs font-semibold text-foreground transition-all focus:border-primary focus:bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
              onChange={e =>
                updateBusinessDocument(doc.id, current => ({
                  ...current,
                  title: e.target.value
                }))
              }
              value={doc.title}
            />
          </div>

          {/* Apple-style Autosave Pill Indicator */}
          <div className="inline-flex items-center gap-1.5 rounded-full border border-border/50 bg-background/60 px-2.5 py-1 text-[0.6875rem] font-medium">
            <span
              className={cn(
                'size-1.5 rounded-full transition-colors',
                autosave === 'saving'
                  ? 'bg-amber-500 animate-pulse'
                  : 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]'
              )}
            />
            <span className="text-muted-foreground">
              {autosave === 'saving' ? 'Saving changes...' : 'Saved'}
            </span>
          </div>
        </div>

        {/* Center Controls: Template, Language, Undo/Redo */}
        <div className="flex flex-wrap items-center gap-2">
          {availableTemplates.length > 0 && (
            <select
              aria-label="Template"
              className="h-8 rounded-xl border border-border/70 bg-background/80 px-3 text-xs font-medium text-foreground transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              onChange={e =>
                updateBusinessDocument(doc.id, current => ({
                  ...current,
                  templateId: e.target.value
                }))
              }
              value={doc.templateId}
            >
              {availableTemplates.map(tpl => (
                <option key={tpl.id} value={tpl.id}>
                  Template: {tpl.name}
                </option>
              ))}
            </select>
          )}

          <select
            aria-label="Document Language"
            className="h-8 rounded-xl border border-border/70 bg-background/80 px-2.5 text-xs font-medium text-foreground transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            onChange={e =>
              updateBusinessDocument(doc.id, current => ({
                ...current,
                language: e.target.value as DocumentLanguage
              }))
            }
            value={doc.language}
          >
            <option value="fr">Français (FR)</option>
            <option value="en">English (EN)</option>
          </select>

          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-border/70 bg-background/80 px-3 text-xs font-medium text-muted-foreground transition hover:border-primary/40 hover:bg-muted hover:text-foreground disabled:opacity-40"
            disabled={!canUseAi || aiBusy !== null}
            onClick={handleTranslateDocument}
            title="Switch language and translate summary"
            type="button"
          >
            <Codicon name="globe" size="0.85rem" />
            <span>AI Translate</span>
          </button>

          {/* Apple-style Unified Undo/Redo Segment */}
          <div className="inline-flex items-center rounded-xl border border-border/70 bg-background/80 p-0.5">
            <button
              aria-label="Undo"
              className="rounded-lg p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-30"
              disabled={!canUndoDocument(doc.id)}
              onClick={() => void undoDocumentChange(doc.id)}
              title="Undo (⌘Z / Ctrl+Z)"
              type="button"
            >
              <Codicon name="discard" size="0.85rem" />
            </button>
            <span className="h-3.5 w-px bg-border/80" />
            <button
              aria-label="Redo"
              className="rounded-lg p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-30"
              disabled={!canRedoDocument(doc.id)}
              onClick={() => void redoDocumentChange(doc.id)}
              title="Redo (⌘⇧Z / Ctrl+Y)"
              type="button"
            >
              <Codicon name="redo" size="0.85rem" />
            </button>
          </div>

          <button
            aria-label="Duplicate Document"
            className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-border/70 bg-background/80 px-3 text-xs font-medium text-muted-foreground transition hover:border-primary/40 hover:bg-muted hover:text-foreground"
            onClick={handleDuplicate}
            type="button"
          >
            <Codicon name="copy" size="0.85rem" />
            <span>Duplicate</span>
          </button>

          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-border/70 bg-background/80 px-3 text-xs font-medium text-muted-foreground transition hover:border-primary/40 hover:bg-muted hover:text-foreground disabled:opacity-40"
            disabled={!canUseAi}
            onClick={handleAskInChat}
            type="button"
          >
            <Codicon name="comment-discussion" size="0.85rem" />
            <span>Ask in Chat</span>
          </button>
        </div>

        {/* Right Controls: Apple Export Buttons */}
        <div className="flex flex-wrap items-center gap-1.5">
          {supportedFormats.map(fmt => (
            <button
              className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-primary px-3.5 text-xs font-semibold text-primary-foreground shadow-sm transition hover:brightness-105 active:scale-[0.98]"
              key={fmt}
              onClick={() => handleExport(fmt)}
              type="button"
            >
              <Codicon name="export" size="0.85rem" />
              Export {fmt.toUpperCase()}
            </button>
          ))}
        </div>
      </header>

      {/* Export & Validation Status Strip */}
      {(lastExportInfo || validation.warnings.length > 0) && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 bg-muted/40 px-6 py-2 text-xs backdrop-blur-xs">
          {lastExportInfo ? (
            <span className="flex items-center gap-1.5 font-semibold text-emerald-600 dark:text-emerald-400" role="status">
              <Codicon name="check" size="0.85rem" />
              {lastExportInfo}
            </span>
          ) : (
            <span />
          )}
          {validation.warnings.length > 0 && (
            <span className="flex items-center gap-1 text-[0.6875rem] text-amber-600 dark:text-amber-400">
              <Codicon name="warning" size="0.75rem" />
              Note: {validation.warnings[0]}
            </span>
          )}
        </div>
      )}

      {/* Split-Screen Editor + Live Preview */}
      <div className="grid flex-1 min-h-0 grid-cols-1 lg:grid-cols-2">
        <div className="overflow-y-auto p-6 scroll-smooth">
          <DocumentForms
            activeSlideIndex={activeSlideIndex}
            aiBusy={aiBusy}
            canUseAi={canUseAi}
            document={doc}
            onConvertQuoteToInvoice={handleConvertQuote}
            onReplaceScanFile={handleReplaceScanFile}
            onRunAi={handleRunAi}
            onSelectSlide={setActiveSlideIndex}
            onUpdateData={handleUpdateData}
          />
        </div>
        <div className="min-h-[420px] overflow-hidden border-t border-border/70 lg:border-l lg:border-t-0">
          <DocumentPreview
            activeSlideIndex={activeSlideIndex}
            document={doc}
            onSelectSlide={setActiveSlideIndex}
          />
        </div>
      </div>
    </div>
  )
}
