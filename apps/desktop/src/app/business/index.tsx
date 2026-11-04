import { useStore } from '@nanostores/react'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { $terminalTakeover } from '@/app/right-sidebar/store'
import { Codicon } from '@/components/ui/codicon'
import { cn } from '@/lib/utils'
import { queueComposerSeed } from '@/store/composer'
import { notify } from '@/store/notifications'

import { NEW_CHAT_ROUTE } from '../routes'

import { DocumentWorkspace } from './components/editor/document-workspace'
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
      <div className="absolute inset-x-4 top-3 -bottom-6 overflow-hidden rounded-t-xl bg-card border border-border/60 shadow-[0_10px_30px_-12px_rgba(0,0,0,0.25)] dark:shadow-[0_10px_30px_-12px_rgba(0,0,0,0.6)]">
        <div className="h-[42%]" style={{ background: 'linear-gradient(135deg,#0053FD,#0038A8)' }} />
        <div className="space-y-1.5 p-3">
          <span className="block h-1.5 w-1/2 rounded-full bg-primary/80" />
          <span className={cn(bar, 'w-11/12')} />
          <span className={cn(bar, 'w-4/5')} />
        </div>
      </div>
    )
  }

  const head = variant === 'invoice' ? 'bg-[#C98A2B]' : 'bg-primary'

  return (
    <div className="absolute inset-x-4 top-3 -bottom-6 rounded-t-xl bg-card border border-border/60 p-3.5 shadow-[0_10px_30px_-12px_rgba(0,0,0,0.25)] dark:shadow-[0_10px_30px_-12px_rgba(0,0,0,0.6)]">
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
    if (!canStartChat) {
      return
    }

    scanFileInputRef.current?.click()
  }

  const handleScanFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]

    if (!file) {
      return
    }

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
    <div className="flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden bg-background text-foreground pt-(--titlebar-height)">
      <div className="mx-auto w-full max-w-5xl px-8 pb-24 pt-6">
        <input
          accept=".pdf,.jpg,.jpeg,.png"
          aria-label="Upload file for Scan to text"
          className="hidden"
          onChange={handleScanFileChange}
          ref={scanFileInputRef}
          type="file"
        />

        <ProfileModal onClose={() => setProfileOpen(false)} open={profileOpen} />

        {/* Apple-style Hero Header */}
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border/50 pb-6">
          <div className="flex items-start gap-4">
            <div
              className="grid size-13 shrink-0 place-items-center rounded-2xl text-white shadow-lg transition-transform hover:scale-105"
              style={{
                background: 'linear-gradient(145deg,#3D7BFF,#0038A8)',
                boxShadow: '0 10px 24px -10px rgba(0,83,253,.6)'
              }}
            >
              <Codicon name="briefcase" size="1.5rem" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-2.5 py-0.5 text-[0.6875rem] font-semibold text-primary backdrop-blur-xs">
                  <span className="size-1.5 rounded-full bg-primary animate-pulse" />
                  Business Suite 2.0
                </span>
                <span className="text-[0.6875rem] text-muted-foreground">· Offline Grounded</span>
              </div>
              <h1 className="mt-1.5 text-2xl font-bold tracking-tight">Business Hub</h1>
              <p className="mt-1 text-sm text-muted-foreground leading-relaxed">
                Create, edit, preview, validate, and export professional business documents with split-screen precision.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              aria-label="Business & Personal Profiles"
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-border/80 bg-card/80 px-3.5 text-xs font-semibold shadow-2xs backdrop-blur-sm transition-all hover:border-primary/40 hover:bg-muted"
              onClick={() => setProfileOpen(true)}
              type="button"
            >
              <Codicon name="organization" size="0.9rem" />
              Profiles
            </button>
            <button
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-border/80 bg-card/80 px-3.5 text-xs font-semibold shadow-2xs backdrop-blur-sm transition-all hover:border-primary/40 hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartChat}
              onClick={handleScanButton}
              type="button"
            >
              <Codicon name="layers" size="0.9rem" />
              Scan to text
            </button>
            <button
              className="inline-flex h-9 items-center gap-2 rounded-xl px-4 text-xs font-semibold text-white shadow-sm transition hover:brightness-105 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartChat}
              onClick={() => createBusinessDocument('cv')}
              style={{ background: 'linear-gradient(180deg,#3D7BFF,#0053FD)' }}
              type="button"
            >
              <Codicon name="add" size="0.9rem" />
              New document
            </button>
          </div>
        </header>

        {takeover && (
          <p
            className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
            role="status"
          >
            Terminal takeover is on, so chats open in the terminal. Turn it off to start a chat from here.
          </p>
        )}

        {/* Claude-style AI Consultant Bar */}
        <section className="mt-6 space-y-2">
          <form
            className="flex items-center gap-3 rounded-2xl border border-border/80 bg-card/90 p-3.5 shadow-sm backdrop-blur-sm transition-all focus-within:border-primary/60 focus-within:ring-4 focus-within:ring-primary/10"
            onSubmit={event => {
              event.preventDefault()

              if (question.trim()) {
                startChat(question.trim())
              }
            }}
          >
            <div
              className="grid size-9 shrink-0 place-items-center rounded-xl text-white shadow-2xs"
              style={{ background: 'linear-gradient(145deg,#C98A2B,#8a5a12)' }}
            >
              <Codicon name="sparkle" size="1.05rem" />
            </div>
            <div className="min-w-0 flex-1">
              <label className="text-[0.6875rem] font-semibold text-muted-foreground uppercase tracking-wider" htmlFor="business-consultant">
                AI Consultant
              </label>
              <input
                className="w-full bg-transparent text-sm placeholder:text-muted-foreground/60 focus:outline-none disabled:cursor-not-allowed"
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
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
                onClick={() => setQuestion('')}
                type="button"
              >
                <Codicon name="close" size="0.85rem" />
              </button>
            )}
            <button
              className="inline-flex h-8 items-center gap-1.5 rounded-xl px-3.5 text-xs font-semibold text-white shadow-xs transition hover:brightness-105 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartChat || !question.trim()}
              style={{ background: 'linear-gradient(180deg,#B57E23,#8a5a12)' }}
              type="submit"
            >
              Open in chat
            </button>
          </form>

          {/* Quick Consultation Chips */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-[0.6875rem] font-medium text-muted-foreground">Quick queries:</span>
            {CONSULTANT_SUGGESTIONS.map(prompt => (
              <button
                className="rounded-lg border border-border/60 bg-muted/30 px-2 py-0.5 text-[0.6875rem] text-muted-foreground transition hover:border-primary/40 hover:bg-card hover:text-foreground disabled:opacity-40"
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
        <div className="mb-4 mt-9 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold tracking-tight">Interactive builders</h2>
            <span className="rounded-full bg-[#1F8A65]/12 px-2.5 py-0.5 text-[0.6875rem] font-semibold text-[#17694D] dark:text-emerald-400">
              Live Editor + Export
            </span>
          </div>
          <button
            className="text-xs font-semibold text-primary transition hover:underline disabled:opacity-40"
            disabled={!canStartChat}
            onClick={() => startChat(NEW_DOCUMENT_PROMPT)}
            type="button"
          >
            Or draft custom document in chat →
          </button>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {BUILDERS.map(b => (
            <div
              className="group flex flex-col overflow-hidden rounded-2xl border border-border/80 bg-card/90 shadow-2xs transition-all duration-200 hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg"
              key={b.id}
            >
              <button
                aria-label={b.title}
                className="flex flex-1 flex-col text-left disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canStartChat}
                onClick={() => handleOpenBuilder(b.id)}
                type="button"
              >
                <div className="relative h-[135px] w-full overflow-hidden bg-gradient-to-br from-primary/[0.08] to-transparent">
                  <DocLines variant={b.id === 'invoice' ? 'invoice' : b.id === 'deck' ? 'deck' : 'cv'} />
                </div>
                <div className="flex items-start gap-2.5 p-3.5">
                  <span
                    className={cn(
                      'grid size-8 shrink-0 place-items-center rounded-xl shadow-2xs',
                      b.accent === 'gold'
                        ? 'bg-[#C98A2B]/12 text-[#B57E23]'
                        : 'bg-primary/10 text-primary'
                    )}
                  >
                    <Codicon name={b.icon} size="1rem" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">{b.title}</span>
                    <span className="mt-0.5 block text-[0.6875rem] text-muted-foreground">{b.sub}</span>
                  </span>
                  <Codicon
                    className="mt-1 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary"
                    name="chevron-right"
                    size="0.85rem"
                  />
                </div>
              </button>
              <div className="flex items-center justify-between border-t border-border/60 bg-muted/20 px-3.5 py-2">
                <button
                  className="text-[0.6875rem] font-semibold text-primary transition hover:underline disabled:opacity-40"
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
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <h2 className="text-lg font-bold tracking-tight">Recent Documents</h2>
              <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">
                {documents.length}
              </span>
            </div>

            {documents.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <input
                    className="h-7 w-36 rounded-lg border border-border/70 bg-card/80 px-2 pl-6 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:w-48 transition-all"
                    onChange={e => setDocSearch(e.target.value)}
                    placeholder="Search docs..."
                    value={docSearch}
                  />
                  <Codicon className="absolute left-1.5 top-1.5 text-muted-foreground" name="search" size="0.75rem" />
                </div>
                <select
                  aria-label="Filter documents by type"
                  className="h-7 rounded-lg border border-border/70 bg-card/80 px-2 text-xs font-medium text-muted-foreground focus:outline-none"
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
            <div className="rounded-2xl border border-dashed border-border/70 bg-card/40 p-8 text-center text-xs text-muted-foreground backdrop-blur-xs">
              No saved documents yet. Choose a builder above or select a template below to create your first document.
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="rounded-2xl border border-border/60 bg-card/40 p-6 text-center text-xs text-muted-foreground">
              No documents matched your search filter.
            </div>
          ) : (
            <div className="space-y-2">
              {filteredDocuments.map(doc => (
                <div
                  className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/80 bg-card/90 px-4 py-3 shadow-2xs backdrop-blur-sm transition-all hover:border-primary/30"
                  key={doc.id}
                >
                  <div className="min-w-0 flex-1">
                    {renamingId === doc.id ? (
                      <div className="flex items-center gap-2">
                        <input
                          aria-label={`Rename input for ${doc.title}`}
                          autoFocus
                          className="h-7 rounded-lg border border-primary bg-background px-2.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-primary/20"
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
                          className="rounded-lg bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground shadow-2xs transition hover:brightness-105"
                          onClick={() => handleCommitRename(doc.id)}
                          type="button"
                        >
                          Save Name
                        </button>
                        <button
                          aria-label="Cancel rename"
                          className="rounded-lg border border-border/70 bg-background px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted"
                          onClick={() => setRenamingId(null)}
                          type="button"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <button
                          className="truncate text-sm font-semibold hover:text-primary hover:underline transition"
                          onClick={() => openBusinessDocument(doc.id)}
                          type="button"
                        >
                          {doc.title}
                        </button>
                        <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[0.625rem] font-bold uppercase text-primary">
                          {doc.type}
                        </span>
                        <span
                          className={cn(
                            'rounded-md px-1.5 py-0.5 text-[0.625rem] font-semibold uppercase',
                            doc.status === 'final'
                              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                              : 'bg-muted text-muted-foreground'
                          )}
                        >
                          {doc.status}
                        </span>
                      </div>
                    )}
                    <div className="mt-0.5 text-[0.6875rem] text-muted-foreground">
                      Template: {doc.templateId} · Language: {doc.language.toUpperCase()} · Updated{' '}
                      {new Date(doc.updatedAt).toLocaleDateString()}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      aria-label={`Open ${doc.title}`}
                      className="rounded-lg border border-border/70 bg-background/80 px-2.5 py-1 text-xs font-semibold shadow-2xs transition hover:border-primary/40 hover:bg-muted"
                      onClick={() => openBusinessDocument(doc.id)}
                      type="button"
                    >
                      Open
                    </button>
                    <button
                      aria-label={`Duplicate ${doc.title}`}
                      className="rounded-lg border border-border/70 bg-background/80 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:border-primary/40 hover:bg-muted hover:text-foreground"
                      onClick={() => duplicateBusinessDocument(doc.id)}
                      type="button"
                    >
                      Duplicate
                    </button>
                    <button
                      aria-label={`Rename ${doc.title}`}
                      className="rounded-lg border border-border/70 bg-background/80 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:border-primary/40 hover:bg-muted hover:text-foreground"
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
                      className="rounded-lg border border-border/70 bg-background/80 px-2.5 py-1 text-xs font-semibold text-primary transition hover:border-primary/40 hover:bg-primary/10"
                      onClick={() => handleExportRecent(doc)}
                      type="button"
                    >
                      Export PDF
                    </button>
                    <button
                      aria-label={`Delete ${doc.title}`}
                      className="rounded-lg border border-border/70 bg-background/80 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:border-destructive/40 hover:text-destructive"
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
              <h2 className="text-lg font-bold tracking-tight">Template Gallery</h2>
              <p className="text-xs text-muted-foreground">
                8 specialized CV layouts plus OHADA invoices, contracts, investor plans, and 16:9 pitch decks.
              </p>
            </div>
            {/* Apple Segmented Filter */}
            <div className="inline-flex flex-wrap rounded-xl bg-muted/60 p-1 border border-border/40 backdrop-blur-sm">
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
                      ? 'bg-card text-foreground shadow-2xs'
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
                className="flex flex-col justify-between rounded-2xl border border-border/80 bg-card/85 p-4 text-left shadow-2xs backdrop-blur-sm transition-all duration-150 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md disabled:opacity-50"
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
                      className="inline-block size-3 rounded-full shadow-2xs"
                      style={{ backgroundColor: tpl.accentColor }}
                    />
                    <span className="text-[0.625rem] font-bold uppercase tracking-wider text-muted-foreground">
                      {tpl.documentType} · {tpl.fontFamily}
                    </span>
                  </div>
                  <div className="mt-2 text-xs font-bold text-foreground">{tpl.name}</div>
                  <p className="mt-1 text-[0.6875rem] leading-relaxed text-muted-foreground">
                    {tpl.description}
                  </p>
                </div>
                <div className="mt-4 flex items-center gap-1 text-[0.6875rem] font-semibold text-primary">
                  <span>Use template</span>
                  <Codicon name="arrow-right" size="0.75rem" />
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* Scan to text CTA */}
        <div
          className="group relative mt-10 flex w-full flex-wrap items-center justify-between gap-6 overflow-hidden rounded-3xl px-8 py-7 text-left text-white shadow-xl"
          style={{ background: 'linear-gradient(135deg,#0b1020,#12224e 55%,#0a2f6b)' }}
        >
          <span
            className="pointer-events-none absolute inset-0"
            style={{ background: 'radial-gradient(50% 120% at 88% 10%,rgba(61,123,255,.5),transparent 55%)' }}
          />
          <div className="relative z-10 flex-1">
            <span className="inline-flex rounded-full bg-white/15 px-3 py-1 text-[0.6875rem] font-semibold uppercase tracking-wide backdrop-blur-xs">
              OCR & Document Extraction
            </span>
            <span className="mt-3 block text-xl font-bold tracking-tight">Turn photos and PDFs into text</span>
            <span className="mt-2 block max-w-lg text-sm text-white/75 leading-relaxed">
              Upload a PDF, JPG, or PNG to extract text directly into an editable workspace, convert it into an invoice or CV draft, or open in chat. Unclear text is marked [illegible], never guessed.
            </span>
            <div className="mt-5 flex flex-wrap gap-2.5">
              <button
                className="inline-flex h-9 items-center gap-2 rounded-xl bg-white px-4 text-xs font-bold text-[#0a2f6b] shadow-md transition hover:brightness-95 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canStartChat}
                onClick={handleScanButton}
                type="button"
              >
                <Codicon name="cloud-upload" size="0.9rem" />
                Select PDF / Image to Scan
              </button>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-xl border border-white/25 bg-white/10 px-4 text-xs font-semibold text-white backdrop-blur-xs transition hover:bg-white/20 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
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
              {['#f2a65a', '#5a8cf2', '#57b98b'].map((c, i) => (
                <span
                  className="size-16 rounded-xl border-2 border-white/15 shadow-xl backdrop-blur-xs"
                  key={c}
                  style={{
                    background: `linear-gradient(150deg,${c},rgba(0,0,0,.35))`,
                    marginLeft: i ? '-1.25rem' : 0,
                    transform: `rotate(${(i - 1) * 8}deg)`
                  }}
                />
              ))}
            </span>
            <Codicon name="arrow-right" size="1.4rem" />
            <span className="grid h-20 w-16 place-items-center gap-1 rounded-2xl bg-white text-[#0a2f6b] shadow-xl">
              <Codicon name="file" size="1.5rem" />
              <b className="text-[0.625rem] font-bold">Text</b>
            </span>
          </span>
        </div>

        {/* Feature grid */}
        <h2 className="mb-4 mt-10 text-lg font-bold tracking-tight">What the workspace does here</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(f => (
            <div className="rounded-2xl border border-border/80 bg-card/85 p-5 shadow-2xs backdrop-blur-sm transition-all hover:border-primary/30" key={f.title}>
              <span
                className={cn(
                  'mb-3.5 grid size-9 place-items-center rounded-xl shadow-2xs',
                  f.gold ? 'bg-[#C98A2B]/12 text-[#B57E23]' : 'bg-primary/10 text-primary'
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
