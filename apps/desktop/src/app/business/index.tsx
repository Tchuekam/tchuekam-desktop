import { useStore } from '@nanostores/react'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { $terminalTakeover } from '@/app/right-sidebar/store'
import { Codicon } from '@/components/ui/codicon'
import { IS_DESKTOP } from '@/lib/platform'
import { cn } from '@/lib/utils'
import { queueComposerSeed } from '@/store/composer'
import { notify } from '@/store/notifications'

import { NEW_CHAT_ROUTE } from '../routes'

import { DocumentWorkspace } from './components/editor/document-workspace'
import {
  BusinessLocalAiInlineCard,
  BusinessLocalAiModal,
  BusinessLocalAiStatusBadge
} from './components/local-ai/business-local-agent-panel'
import { ProfileModal } from './components/profile/profile-modal'
import { exportBusinessDocument } from './exporters'
import {
  BUILDER_PROMPTS,
  type BuilderId,
  NEW_DOCUMENT_PROMPT,
  SCAN_TO_TEXT_PROMPT
} from './prompts'
import { ALL_TEMPLATES } from './schemas'
import { extractDocumentFromFile } from './services/ai-orchestrator'
import {
  $activeDocumentId,
  $businessDocuments,
  createBusinessDocument,
  deleteBusinessDocument,
  duplicateBusinessDocument,
  openBusinessDocument,
  renameBusinessDocument
} from './store'
import { askBusinessLocalAgent } from './store/local-ai'
import type { BusinessDocument, DocumentTemplate } from './types'

interface Builder {
  accent: 'blue' | 'gold'
  icon: string
  id: BuilderId
  sub: string
  title: string
}

const BUILDERS: Builder[] = [
  { accent: 'blue', icon: 'account', id: 'cv', sub: 'Plain, ATS-friendly structure', title: 'CV / Résumé' },
  { accent: 'gold', icon: 'credit-card', id: 'invoice', sub: 'FCFA · MoMo / Orange Money', title: 'Facture' },
  { accent: 'blue', icon: 'law', id: 'contract', sub: 'Prestation · bail · NDA', title: 'Contrat' },
  { accent: 'blue', icon: 'graph', id: 'deck', sub: 'For investors', title: 'Pitch Deck' },
  { accent: 'blue', icon: 'rocket', id: 'plan', sub: 'Illustrative financial assumptions', title: 'Business Plan' },
  { accent: 'gold', icon: 'checklist', id: 'quote', sub: 'Quick quotation', title: 'Devis' },
  { accent: 'blue', icon: 'mail', id: 'letter', sub: 'FR / EN', title: 'Lettre de motivation' },
  { accent: 'blue', icon: 'verified', id: 'attestation', sub: 'Employment · internship', title: 'Attestation' }
]

interface Feature {
  desc: string
  gold?: boolean
  icon: string
  title: string
}

const FEATURES: Feature[] = [
  {
    desc: 'Attach photos or text PDFs and get their text back. Unclear text is marked, not guessed.',
    icon: 'device-camera',
    title: 'Scan to text'
  },
  {
    desc: 'Create, edit, preview, validate, and export real PDF, DOCX, XLSX, and PPTX documents.',
    gold: true,
    icon: 'file',
    title: 'Interactive Workspace & Export'
  },
  {
    desc: 'ATS keyword matching, deterministic FCFA/EUR/USD billing math, and reusable profiles.',
    icon: 'verified',
    title: 'Validated & Grounded'
  }
]

type TemplateFilter = 'all' | 'cv' | 'finance' | 'legal' | 'strategy'

function filterTemplates(templates: DocumentTemplate[], filter: TemplateFilter): DocumentTemplate[] {
  if (filter === 'all') {
    return templates
  }

  if (filter === 'cv') {
    return templates.filter(t => t.documentType === 'cv')
  }

  if (filter === 'finance') {
    return templates.filter(t => t.documentType === 'invoice' || t.documentType === 'quote')
  }

  if (filter === 'legal') {
    return templates.filter(
      t =>
        t.documentType === 'contract' ||
        t.documentType === 'attestation' ||
        t.documentType === 'letter'
    )
  }

  return templates.filter(t => t.documentType === 'plan' || t.documentType === 'deck')
}

function DocLines({ variant }: { variant: 'cv' | 'invoice' | 'deck' }) {
  const bar = 'block h-[3px] rounded-full bg-foreground/15 dark:bg-foreground/20'

  if (variant === 'deck') {
    return (
      <div className="absolute inset-x-4 top-3 -bottom-6 overflow-hidden rounded-t-xl border border-(--tk-glass-border) bg-card/95 shadow-[0_10px_28px_-12px_rgba(15,23,42,0.22)] transition-transform duration-200 ease-out group-hover:-translate-y-1 dark:shadow-[0_12px_30px_-12px_rgba(0,0,0,0.65)]">
        <div
          className="h-[42%]"
          style={{ background: 'linear-gradient(135deg, var(--tk-indigo), var(--tk-cyan))' }}
        />
        <div className="space-y-1.5 p-3">
          <span className="block h-1.5 w-1/2 rounded-full bg-(--tk-indigo)/80" />
          <span className={cn(bar, 'w-11/12')} />
          <span className={cn(bar, 'w-4/5')} />
        </div>
      </div>
    )
  }

  const head = variant === 'invoice' ? 'bg-(--tk-cyan)' : 'bg-(--tk-indigo)'

  return (
    <div className="absolute inset-x-4 top-3 -bottom-6 rounded-t-xl border border-(--tk-glass-border) bg-card/95 p-3.5 shadow-[0_10px_28px_-12px_rgba(15,23,42,0.22)] transition-transform duration-200 ease-out group-hover:-translate-y-1 dark:shadow-[0_12px_30px_-12px_rgba(0,0,0,0.65)]">
      <span className={cn('mb-2 block h-1.5 w-2/5 rounded-full', head)} />
      <div className="space-y-1.5">
        <span className={cn(bar, 'w-11/12')} />
        <span className={cn(bar, 'w-3/4')} />
        <span className={cn(bar, 'w-5/6')} />
        <div className="flex gap-2 pt-1">
          <span className="flex-1 space-y-1.5">
            <span className={cn(bar, 'block w-full')} />
            <span className={cn(bar, 'block w-3/4')} />
          </span>
          <span className="flex-1 space-y-1.5">
            <span className={cn(bar, 'block w-5/6')} />
            <span className={cn(bar, 'block w-1/2')} />
          </span>
        </div>
        <span className={cn(bar, 'w-2/3')} />
      </div>
    </div>
  )
}

const CONSULTANT_SUGGESTIONS = [
  'Make my CV stronger for a role in Douala',
  'OHADA compliant service invoice in FCFA',
  'Commercial contract with IP & confidentiality clause',
  '16:9 Investor pitch deck structure'
]

export function BusinessView() {
  const navigate = useNavigate()
  const takeover = useStore($terminalTakeover)
  const documents = useStore($businessDocuments)
  const activeDocId = useStore($activeDocumentId)

  const [question, setQuestion] = useState('')
  const [profileOpen, setProfileOpen] = useState(false)
  const [templateFilter, setTemplateFilter] = useState<TemplateFilter>('all')
  const [docSearch, setDocSearch] = useState('')
  const [docTypeFilter, setDocTypeFilter] = useState<string>('all')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [scanning, setScanning] = useState(false)
  const scanFileInputRef = useRef<HTMLInputElement | null>(null)

  const canStartChat = !takeover
  const activeDoc = activeDocId ? documents.find(d => d.id === activeDocId) ?? null : null

  const startChat = (prompt: string) => {
    if (!canStartChat) {
      return
    }

    queueComposerSeed(prompt)
    navigate(NEW_CHAT_ROUTE)
  }

  const handleOpenBuilder = (id: BuilderId) => {
    if (!canStartChat) {
      return
    }

    createBusinessDocument(id)
  }

  const handleScanButton = () => {
    if (!canStartChat || scanning) {
      return
    }

    scanFileInputRef.current?.click()
  }

  const handleScanFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]

    if (!file || scanning) {
      return
    }

    setScanning(true)
    void extractDocumentFromFile(file)
      .then(res => {
        createBusinessDocument('scan', {
          initialData: {
            confidenceNote:
              'Verify all extracted numbers, dates, and names against the original document. Unclear text is marked [illegible].',
            editedText: res.extractedText,
            extractedAt: Date.now(),
            rawText: res.extractedText,
            sourceFileName: res.fileName,
            sourceMimeType: res.mimeType,
            structuredSummary: `Extracted from ${res.fileName}`
          },
          title: `Scan — ${res.fileName}`
        })
        notify({
          kind: 'success',
          message: `Extracted text from ${res.fileName}.`,
          title: 'Scan Complete'
        })
      })
      .catch((err: unknown) => {
        notify({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Scan extraction failed.',
          title: 'Scan Error'
        })
      })
      .finally(() => {
        setScanning(false)

        if (scanFileInputRef.current) {
          scanFileInputRef.current.value = ''
        }
      })
  }

  const handleCommitRename = (docId: string) => {
    const trimmed = renameDraft.trim()

    if (trimmed) {
      renameBusinessDocument(docId, trimmed)
      notify({
        kind: 'success',
        message: `Renamed to "${trimmed}".`,
        title: 'Document Renamed'
      })
    }

    setRenamingId(null)
  }

  const handleExportRecent = (doc: BusinessDocument) => {
    try {
      const res = exportBusinessDocument(doc, 'pdf')
      notify({
        kind: 'success',
        message: `Exported ${res.filename}.`,
        title: 'Export PDF Complete'
      })
    } catch (err: unknown) {
      notify({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Export failed.',
        title: 'Export Error'
      })
    }
  }

  const handleDeleteRecent = (docId: string, title: string) => {
    deleteBusinessDocument(docId)
    notify({
      kind: 'info',
      message: `Deleted "${title}".`,
      title: 'Document Deleted'
    })
  }

  if (activeDoc) {
    return (
      <DocumentWorkspace
        document={activeDoc}
        onBack={() => openBusinessDocument(null)}
        onOpenChat={startChat}
      />
    )
  }

  const visibleTemplates = filterTemplates(ALL_TEMPLATES, templateFilter)

  const filteredDocuments = documents.filter(doc => {
    const matchesSearch =
      !docSearch.trim() ||
      doc.title.toLowerCase().includes(docSearch.toLowerCase()) ||
      doc.type.toLowerCase().includes(docSearch.toLowerCase())

    const matchesType = docTypeFilter === 'all' || doc.type === docTypeFilter

    return matchesSearch && matchesType
  })

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden bg-background text-foreground pt-(--titlebar-height)">
      <div aria-hidden className="tk-ambient-halo pointer-events-none absolute inset-x-0 top-0 z-0 h-80" />
      <div className="relative z-1 mx-auto w-full max-w-5xl px-4 pb-20 pt-4 sm:px-6 md:px-8 md:pb-24 md:pt-[calc(var(--titlebar-height)+0.75rem)]">
        <input
          accept=".pdf,.jpg,.jpeg,.png"
          aria-label="Upload file for Scan to text"
          className="hidden"
          onChange={handleScanFileChange}
          ref={scanFileInputRef}
          type="file"
        />

        <ProfileModal onClose={() => setProfileOpen(false)} open={profileOpen} />
        {IS_DESKTOP ? <BusinessLocalAiModal /> : null}

        {/* Executive Hero Header */}
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-(--tk-glass-border) pb-6">
          <div className="flex items-start gap-4">
            <div className="tk-btn-primary grid size-13 shrink-0 place-items-center rounded-2xl text-white">
              <Codicon name="briefcase" size="1.45rem" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-(--tk-indigo-border) bg-(--tk-indigo-soft) px-2.5 py-0.5 text-[0.6875rem] font-semibold text-(--tk-indigo-text) backdrop-blur-xs">
                  <span aria-hidden className="size-1.5 rounded-full bg-linear-to-r from-(--tk-indigo) to-(--tk-cyan)" />
                  Business Suite 2.0
                </span>
                <span className="text-[0.6875rem] font-medium text-muted-foreground">· Offline Grounded</span>
              </div>
              <h1 className="mt-1.5 text-[1.625rem] font-semibold tracking-[-0.025em] sm:text-[1.875rem]">
                Business Hub
              </h1>
              <p className="mt-1 text-sm leading-relaxed text-(--ui-text-secondary)">
                Create, edit, preview, validate, and export professional business documents with split-screen precision.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {IS_DESKTOP ? <BusinessLocalAiStatusBadge /> : null}
            <button
              aria-label="Business & Personal Profiles"
              className="tk-glass-subtle tk-surface-hover inline-flex h-9 items-center gap-2 rounded-xl px-3.5 text-xs font-semibold hover:border-(--tk-indigo-border) hover:bg-muted/70"
              onClick={() => setProfileOpen(true)}
              type="button"
            >
              <Codicon name="organization" size="0.9rem" />
              Profiles
            </button>
            <button
              className="tk-glass-subtle tk-surface-hover inline-flex h-9 items-center gap-2 rounded-xl px-3.5 text-xs font-semibold hover:border-(--tk-indigo-border) hover:bg-muted/70 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartChat}
              onClick={handleScanButton}
              type="button"
            >
              <Codicon name="layers" size="0.9rem" />
              Scan to text
            </button>
            <button
              className="tk-btn-primary inline-flex h-9 items-center gap-2 rounded-xl px-4 text-xs font-semibold text-white active:scale-[0.985] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartChat}
              onClick={() => createBusinessDocument('cv')}
              type="button"
            >
              <Codicon name="add" size="0.9rem" />
              New document
            </button>
          </div>
        </header>

        {takeover && (
          <p
            className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 backdrop-blur-xs dark:text-amber-300"
            role="status"
          >
            Terminal takeover is on, so chats open in the terminal. Turn it off to start a chat from here.
          </p>
        )}

        {/* AI Consultant Bar */}
        <section className="mt-6 space-y-2.5">
          <form
            className="tk-glass-elevated flex flex-wrap items-center gap-3 rounded-2xl p-3.5 transition-all duration-200 focus-within:border-(--tk-indigo-border) focus-within:ring-4 focus-within:ring-(--tk-indigo-glow)"
            onSubmit={event => {
              event.preventDefault()

              if (question.trim()) {
                startChat(question.trim())
              }
            }}
          >
            <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-linear-to-br from-(--tk-indigo) to-(--tk-cyan) text-white shadow-xs">
              <Codicon name="sparkle" size="1.05rem" />
            </div>
            <div className="min-w-0 flex-1">
              <label
                className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-(--ui-text-secondary)"
                htmlFor="business-consultant"
              >
                AI Consultant
              </label>
              <input
                className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none disabled:cursor-not-allowed"
                disabled={!canStartChat}
                id="business-consultant"
                onChange={event => setQuestion(event.target.value)}
                placeholder="Ask for guidance: “Make my CV stronger for a role in Douala”…"
                value={question}
              />
            </div>
            {question && (
              <button
                aria-label="Clear question"
                className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onClick={() => setQuestion('')}
                type="button"
              >
                <Codicon name="close" size="0.85rem" />
              </button>
            )}
            {IS_DESKTOP ? (
              <button
                className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-(--tk-cyan-border) bg-(--tk-cyan-soft) px-3 text-xs font-semibold text-(--tk-cyan-text) transition-colors hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canStartChat || !question.trim()}
                onClick={() => void askBusinessLocalAgent(question.trim())}
                type="button"
              >
                <Codicon name="chip" size="0.85rem" />
                Ask Local Agent
              </button>
            ) : null}
            <button
              className="tk-btn-primary inline-flex h-8 items-center gap-1.5 rounded-xl px-3.5 text-xs font-semibold text-white active:scale-[0.985] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartChat || !question.trim()}
              type="submit"
            >
              Open in chat
            </button>
          </form>

          {IS_DESKTOP ? <BusinessLocalAiInlineCard /> : null}

          {/* Quick Consultation Chips */}
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
            <span className="text-[0.6875rem] font-medium text-muted-foreground">Quick queries:</span>
            {CONSULTANT_SUGGESTIONS.map(prompt => (
              <button
                className="rounded-lg border border-(--tk-glass-border) bg-(--tk-glass-subtle-bg) px-2.5 py-1 text-[0.7rem] text-(--ui-text-secondary) backdrop-blur-xs transition-all duration-150 hover:border-(--tk-indigo-border) hover:bg-[color-mix(in_srgb,var(--tk-indigo-soft)_65%,transparent)] hover:text-foreground disabled:opacity-40"
                disabled={!canStartChat}
                key={prompt}
                onClick={() => setQuestion(prompt)}
                type="button"
              >
                {prompt}
              </button>
            ))}
          </div>
        </section>

        {/* Quick Creation / Interactive Builders */}
        <div className="mb-4 mt-10 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold tracking-tight">Interactive builders</h2>
            <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-0.5 text-[0.6875rem] font-semibold text-emerald-700 dark:text-emerald-400">
              Live Editor + Export
            </span>
          </div>
          <button
            className="text-xs font-semibold text-(--tk-indigo-text) transition-colors hover:underline disabled:opacity-40"
            disabled={!canStartChat}
            onClick={() => startChat(NEW_DOCUMENT_PROMPT)}
            type="button"
          >
            Or draft custom document in chat →
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
          {BUILDERS.map(b => (
            <div
              className="tk-glass tk-surface-hover group flex flex-col overflow-hidden rounded-2xl hover:-translate-y-0.5 hover:border-(--tk-indigo-border) hover:shadow-(--tk-glass-elevated-shadow)"
              key={b.id}
            >
              <button
                aria-label={b.title}
                className="flex flex-1 flex-col text-left disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canStartChat}
                onClick={() => handleOpenBuilder(b.id)}
                type="button"
              >
                <div
                  className={cn(
                    'relative h-[135px] w-full overflow-hidden bg-gradient-to-br to-transparent',
                    b.accent === 'gold'
                      ? 'from-[color-mix(in_srgb,var(--tk-cyan)_11%,transparent)]'
                      : 'from-[color-mix(in_srgb,var(--tk-indigo)_11%,transparent)]'
                  )}
                >
                  <DocLines variant={b.id === 'invoice' ? 'invoice' : b.id === 'deck' ? 'deck' : 'cv'} />
                </div>
                <div className="flex items-start gap-2.5 p-3.5">
                  <span
                    className={cn(
                      'grid size-8 shrink-0 place-items-center rounded-xl',
                      b.accent === 'gold'
                        ? 'bg-(--tk-cyan-soft) text-(--tk-cyan-text)'
                        : 'bg-(--tk-indigo-soft) text-(--tk-indigo-text)'
                    )}
                  >
                    <Codicon name={b.icon} size="1rem" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">{b.title}</span>
                    <span className="mt-0.5 block text-[0.6875rem] text-muted-foreground">{b.sub}</span>
                  </span>
                  <Codicon
                    className="mt-1 text-muted-foreground transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-(--tk-indigo-text)"
                    name="chevron-right"
                    size="0.85rem"
                  />
                </div>
              </button>
              <div className="flex items-center justify-between border-t border-(--tk-glass-border) bg-(--ui-bg-tertiary)/40 px-3.5 py-2">
                <button
                  className="text-[0.6875rem] font-semibold text-(--tk-indigo-text) transition hover:underline disabled:opacity-40"
                  disabled={!canStartChat}
                  onClick={() => handleOpenBuilder(b.id)}
                  type="button"
                >
                  Open Studio
                </button>
                <button
                  aria-label={`Draft ${b.title} in chat`}
                  className="text-[0.6875rem] font-medium text-muted-foreground transition hover:text-foreground disabled:opacity-40"
                  disabled={!canStartChat}
                  onClick={() => startChat(BUILDER_PROMPTS[b.id])}
                  type="button"
                >
                  Chat prompt
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Recent Documents Section */}
        <section className="mt-10">
          <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <h2 className="text-lg font-semibold tracking-tight">Recent Documents</h2>
              <span className="rounded-full border border-(--tk-glass-border) bg-(--tk-glass-subtle-bg) px-2.5 py-0.5 text-xs font-semibold tabular-nums text-(--ui-text-secondary)">
                {documents.length}
              </span>
            </div>

            {documents.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <input
                    className="h-8 w-40 rounded-xl border border-(--tk-glass-border) bg-(--tk-glass-subtle-bg) px-2.5 pl-7 text-xs text-foreground placeholder:text-muted-foreground/60 transition-all focus:w-52 focus:border-(--tk-indigo) focus:outline-none focus:ring-2 focus:ring-(--tk-indigo-glow)"
                    onChange={e => setDocSearch(e.target.value)}
                    placeholder="Search docs..."
                    value={docSearch}
                  />
                  <Codicon className="absolute left-2 top-2 text-muted-foreground" name="search" size="0.75rem" />
                </div>
                <select
                  aria-label="Filter documents by type"
                  className="h-8 rounded-xl border border-(--tk-glass-border) bg-(--tk-glass-subtle-bg) px-2.5 text-xs font-medium text-(--ui-text-secondary) focus:border-(--tk-indigo) focus:outline-none focus:ring-2 focus:ring-(--tk-indigo-glow)"
                  onChange={e => setDocTypeFilter(e.target.value)}
                  value={docTypeFilter}
                >
                  <option value="all">All types</option>
                  <option value="cv">CV / Résumé</option>
                  <option value="invoice">Facture</option>
                  <option value="quote">Devis</option>
                  <option value="contract">Contrat</option>
                  <option value="deck">Pitch Deck</option>
                  <option value="plan">Business Plan</option>
                  <option value="letter">Lettre</option>
                  <option value="attestation">Attestation</option>
                  <option value="scan">Scan</option>
                </select>
              </div>
            )}
          </div>

          {documents.length === 0 ? (
            <div className="tk-glass-subtle flex flex-col items-center gap-3 rounded-2xl border-dashed p-10 text-center">
              <span className="grid size-11 place-items-center rounded-xl bg-(--tk-indigo-soft) text-(--tk-indigo-text)">
                <Codicon name="file-text" size="1.25rem" />
              </span>
              <p className="max-w-md text-xs leading-relaxed text-(--ui-text-secondary)">
                No saved documents yet. Choose a builder above or select a template below to create your first document.
              </p>
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="tk-glass-subtle rounded-2xl p-6 text-center text-xs text-muted-foreground">
              No documents matched your search filter.
            </div>
          ) : (
            <div className="space-y-2.5">
              {filteredDocuments.map(doc => (
                <div
                  className="tk-glass-subtle tk-surface-hover flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3.5 hover:border-(--tk-indigo-border)"
                  key={doc.id}
                >
                  <div className="min-w-0 flex-1">
                    {renamingId === doc.id ? (
                      <div className="flex items-center gap-2">
                        <input
                          aria-label={`Rename input for ${doc.title}`}
                          autoFocus
                          className="h-8 rounded-xl border border-(--tk-indigo) bg-background px-2.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-(--tk-indigo-glow)"
                          onChange={e => setRenameDraft(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              handleCommitRename(doc.id)
                            } else if (e.key === 'Escape') {
                              e.preventDefault()
                              setRenamingId(null)
                            }
                          }}
                          value={renameDraft}
                        />
                        <button
                          className="tk-btn-primary rounded-xl px-3 py-1 text-xs font-semibold text-white"
                          onClick={() => handleCommitRename(doc.id)}
                          type="button"
                        >
                          Save Name
                        </button>
                        <button
                          aria-label="Cancel rename"
                          className="rounded-xl border border-(--tk-glass-border) bg-background/70 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                          onClick={() => setRenamingId(null)}
                          type="button"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          className="truncate text-sm font-semibold transition-colors hover:text-(--tk-indigo-text) hover:underline"
                          onClick={() => openBusinessDocument(doc.id)}
                          type="button"
                        >
                          {doc.title}
                        </button>
                        <span className="rounded-md bg-(--tk-indigo-soft) px-1.5 py-0.5 text-[0.625rem] font-bold uppercase text-(--tk-indigo-text)">
                          {doc.type}
                        </span>
                        <span
                          className={cn(
                            'rounded-md px-1.5 py-0.5 text-[0.625rem] font-semibold uppercase',
                            doc.status === 'final'
                              ? 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-400'
                              : 'bg-muted text-muted-foreground'
                          )}
                        >
                          {doc.status}
                        </span>
                      </div>
                    )}
                    <div className="mt-1 text-[0.6875rem] tabular-nums text-muted-foreground">
                      Template: {doc.templateId} · Language: {doc.language.toUpperCase()} · Updated{' '}
                      {new Date(doc.updatedAt).toLocaleDateString()}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      aria-label={`Open ${doc.title}`}
                      className="rounded-xl border border-(--tk-glass-border) bg-background/70 px-2.5 py-1 text-xs font-semibold transition hover:border-(--tk-indigo-border) hover:bg-muted"
                      onClick={() => openBusinessDocument(doc.id)}
                      type="button"
                    >
                      Open
                    </button>
                    <button
                      aria-label={`Duplicate ${doc.title}`}
                      className="rounded-xl border border-(--tk-glass-border) bg-background/70 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:border-(--tk-indigo-border) hover:bg-muted hover:text-foreground"
                      onClick={() => duplicateBusinessDocument(doc.id)}
                      type="button"
                    >
                      Duplicate
                    </button>
                    <button
                      aria-label={`Rename ${doc.title}`}
                      className="rounded-xl border border-(--tk-glass-border) bg-background/70 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:border-(--tk-indigo-border) hover:bg-muted hover:text-foreground"
                      onClick={() => {
                        setRenamingId(doc.id)
                        setRenameDraft(doc.title)
                      }}
                      type="button"
                    >
                      Rename
                    </button>
                    <button
                      aria-label={`Export ${doc.title} PDF`}
                      className="rounded-xl border border-(--tk-indigo-border) bg-(--tk-indigo-soft) px-2.5 py-1 text-xs font-semibold text-(--tk-indigo-text) transition hover:brightness-105"
                      onClick={() => handleExportRecent(doc)}
                      type="button"
                    >
                      Export PDF
                    </button>
                    <button
                      aria-label={`Delete ${doc.title}`}
                      className="rounded-xl border border-(--tk-glass-border) bg-background/70 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:border-destructive/40 hover:text-destructive"
                      onClick={() => handleDeleteRecent(doc.id, doc.title)}
                      type="button"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Template Gallery */}
        <section className="mt-10">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Template Gallery</h2>
              <p className="text-xs text-muted-foreground">
                8 specialized CV layouts plus OHADA invoices, contracts, investor plans, and 16:9 pitch decks.
              </p>
            </div>
            {/* Segmented Filter */}
            <div className="tk-glass-subtle inline-flex max-w-full flex-wrap rounded-xl p-1">
              {(
                [
                  ['all', 'All Templates'],
                  ['cv', 'CV / Résumé (8)'],
                  ['finance', 'Invoices & Quotes'],
                  ['legal', 'Contracts & HR'],
                  ['strategy', 'Business Plan & Deck']
                ] as const
              ).map(([id, label]) => (
                <button
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-xs font-semibold transition-all duration-150',
                    templateFilter === id
                      ? 'bg-card text-foreground shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                  key={id}
                  onClick={() => setTemplateFilter(id)}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {visibleTemplates.map(tpl => (
              <button
                className="tk-glass-subtle tk-surface-hover group flex flex-col justify-between rounded-2xl p-4 text-left hover:-translate-y-0.5 hover:border-(--tk-indigo-border) hover:shadow-(--tk-glass-shadow) disabled:opacity-50"
                disabled={!canStartChat}
                key={tpl.id}
                onClick={() =>
                  createBusinessDocument(tpl.documentType, {
                    templateId: tpl.id
                  })
                }
                type="button"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className="inline-block size-3 rounded-full ring-2 ring-inset ring-black/10 dark:ring-white/15"
                      style={{ backgroundColor: tpl.accentColor }}
                    />
                    <span className="text-[0.625rem] font-semibold uppercase tracking-wider text-muted-foreground">
                      {tpl.documentType} · {tpl.fontFamily}
                    </span>
                  </div>
                  <div className="mt-2.5 text-xs font-semibold text-foreground">{tpl.name}</div>
                  <p className="mt-1 text-[0.6875rem] leading-relaxed text-muted-foreground">
                    {tpl.description}
                  </p>
                </div>
                <div className="mt-4 flex items-center gap-1 text-[0.6875rem] font-semibold text-(--tk-indigo-text)">
                  <span>Use template</span>
                  <Codicon className="transition-transform duration-150 group-hover:translate-x-0.5" name="arrow-right" size="0.75rem" />
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* Scan to text CTA */}
        <div
          className="group relative mt-8 flex w-full flex-wrap items-center justify-between gap-4 overflow-hidden rounded-3xl border border-white/12 px-5 py-6 text-left text-white shadow-(--tk-glass-elevated-shadow) sm:mt-10 sm:gap-6 sm:px-8 sm:py-7"
          style={{ background: 'linear-gradient(135deg,#0b1020 0%,#121b38 55%,#161f45 100%)' }}
        >
          <span
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                'radial-gradient(50% 110% at 88% 12%,rgba(99,102,241,0.34),transparent 58%),radial-gradient(40% 90% at 65% 100%,rgba(56,189,248,0.18),transparent 62%)'
            }}
          />
          <div className="relative z-10 flex-1">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[0.6875rem] font-semibold uppercase tracking-wide backdrop-blur-xs">
              <span aria-hidden className="size-1.5 rounded-full bg-sky-400" />
              OCR & Document Extraction
            </span>
            <span className="mt-3 block text-xl font-semibold tracking-tight">Turn photos and PDFs into text</span>
            <span className="mt-2 block max-w-lg text-sm leading-relaxed text-slate-200/80">
              Upload a PDF, JPG, or PNG to extract text directly into an editable workspace, convert it into an invoice or CV draft, or open in chat. Unclear text is marked [illegible], never guessed.
            </span>
            <div className="mt-5 flex flex-wrap gap-2.5">
              <button
                className="inline-flex h-9 items-center gap-2 rounded-xl bg-white px-4 text-xs font-bold text-[#0f172a] shadow-md transition hover:bg-slate-100 active:scale-[0.985] disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canStartChat || scanning}
                onClick={handleScanButton}
                type="button"
              >
                <Codicon name={scanning ? 'loading' : 'cloud-upload'} size="0.9rem" spinning={scanning} />
                {scanning ? 'Scanning…' : 'Select PDF / Image to Scan'}
              </button>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 text-xs font-semibold text-white backdrop-blur-xs transition hover:bg-white/18 active:scale-[0.985] disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canStartChat}
                onClick={() => startChat(SCAN_TO_TEXT_PROMPT)}
                type="button"
              >
                <Codicon name="comment-discussion" size="0.9rem" />
                Scan in Chat
              </button>
            </div>
          </div>
          <span className="relative z-10 hidden shrink-0 items-center gap-3 sm:flex">
            <span className="flex">
              {[
                'linear-gradient(150deg, rgba(99,102,241,0.9), rgba(15,23,42,0.55))',
                'linear-gradient(150deg, rgba(56,189,248,0.85), rgba(15,23,42,0.55))',
                'linear-gradient(150deg, rgba(226,232,240,0.92), rgba(71,85,105,0.55))'
              ].map((bg, i) => (
                <span
                  className="size-16 rounded-xl border border-white/20 shadow-xl backdrop-blur-xs"
                  key={i}
                  style={{
                    background: bg,
                    marginLeft: i ? '-1.25rem' : 0,
                    transform: `rotate(${(i - 1) * 7}deg)`
                  }}
                />
              ))}
            </span>
            <Codicon className="text-sky-300" name="arrow-right" size="1.35rem" />
            <span className="grid h-20 w-16 place-items-center gap-1 rounded-2xl border border-white/20 bg-white/95 text-[#0f172a] shadow-xl">
              <Codicon name="file" size="1.45rem" />
              <b className="text-[0.625rem] font-bold">Text</b>
            </span>
          </span>
        </div>

        {/* Feature grid */}
        <h2 className="mb-4 mt-10 text-lg font-semibold tracking-tight">What the workspace does here</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(f => (
            <div
              className="tk-glass-subtle tk-surface-hover rounded-2xl p-5 hover:border-(--tk-indigo-border)"
              key={f.title}
            >
              <span
                className={cn(
                  'mb-3.5 grid size-9 place-items-center rounded-xl',
                  f.gold
                    ? 'bg-(--tk-cyan-soft) text-(--tk-cyan-text)'
                    : 'bg-(--tk-indigo-soft) text-(--tk-indigo-text)'
                )}
              >
                <Codicon name={f.icon} size="1.05rem" />
              </span>
              <div className="text-sm font-semibold">{f.title}</div>
              <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{f.desc}</p>
            </div>
          ))}
        </div>

        <p className="mt-8 text-xs text-muted-foreground">
          Drafts can contain errors. Check amounts, dates, names and legal terms before you sign or send.
        </p>
      </div>
    </div>
  )
}
