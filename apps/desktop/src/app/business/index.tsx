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
    <div className="flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden bg-background text-foreground pt-(--titlebar-height)">
      <div className="mx-auto w-full max-w-5xl px-4 pb-20 pt-4 sm:px-6 md:px-8 md:pb-24 md:pt-[calc(var(--titlebar-height)+0.75rem)]">
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
            {IS_DESKTOP ? <BusinessLocalAiStatusBadge /> : null}
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
            {IS_DESKTOP ? (
              <button
                className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/10 px-3 text-xs font-semibold text-primary transition hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canStartChat || !question.trim()}
                onClick={() => void askBusinessLocalAgent(question.trim())}
                type="button"
              >
