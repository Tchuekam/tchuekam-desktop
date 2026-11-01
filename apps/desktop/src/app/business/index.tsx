import { useStore } from '@nanostores/react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { $terminalTakeover } from '@/app/right-sidebar/store'
import { Codicon } from '@/components/ui/codicon'
import { cn } from '@/lib/utils'
import { queueComposerSeed } from '@/store/composer'

import { NEW_CHAT_ROUTE } from '../routes'

import { BUILDER_PROMPTS, type BuilderId, NEW_DOCUMENT_PROMPT, SCAN_TO_TEXT_PROMPT } from './prompts'

/**
 * Business Hub — entry point for business documents.
 * Every action opens a new chat with a prompt seeded into the composer; the
 * assistant does the drafting and text extraction. Nothing is sent until the
 * user submits it. While terminal takeover is on, new chats would open in the
 * terminal, so the actions are disabled and the page says why.
 */

interface Builder {
  id: BuilderId
  title: string
  sub: string
  icon: string
  accent: 'blue' | 'gold'
}

const BUILDERS: Builder[] = [
  { id: 'cv', title: 'CV / Résumé', sub: 'Plain, ATS-friendly structure', icon: 'account', accent: 'blue' },
  { id: 'invoice', title: 'Facture', sub: 'FCFA · MoMo / Orange Money', icon: 'credit-card', accent: 'gold' },
  { id: 'contract', title: 'Contrat', sub: 'Prestation · bail · NDA', icon: 'law', accent: 'blue' },
  { id: 'deck', title: 'Pitch Deck', sub: 'For investors', icon: 'graph', accent: 'blue' },
  { id: 'plan', title: 'Business Plan', sub: 'Illustrative financial assumptions', icon: 'rocket', accent: 'blue' },
  { id: 'quote', title: 'Devis', sub: 'Quick quotation', icon: 'checklist', accent: 'gold' },
  { id: 'letter', title: 'Lettre de motivation', sub: 'FR / EN', icon: 'mail', accent: 'blue' },
  { id: 'attestation', title: 'Attestation', sub: 'Employment · internship', icon: 'verified', accent: 'blue' }
]

interface Feature {
  title: string
  desc: string
  icon: string
  gold?: boolean
}

const FEATURES: Feature[] = [
  {
    title: 'Scan to text',
    desc: 'Attach photos or text PDFs and get their text back. Unclear text is marked, not guessed.',
    icon: 'device-camera'
  },
  {
    title: 'Guided drafting',
    desc: 'The assistant asks for the details, then drafts the text in the chat.',
    icon: 'file',
    gold: true
  },
  {
    title: 'CV review',
    desc: 'Ask the assistant for ATS-style feedback on a résumé before you send it.',
    icon: 'verified'
  }
]

function DocLines({ variant }: { variant: 'cv' | 'invoice' | 'deck' }) {
  const bar = 'block h-[3px] rounded-full bg-foreground/10'

  if (variant === 'deck') {
    return (
      <div className="absolute inset-x-4 top-3 -bottom-6 overflow-hidden rounded-t-md bg-white p-0 shadow-[0_10px_30px_-12px_rgba(0,0,0,0.3)]">
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
    <div className="absolute inset-x-4 top-3 -bottom-6 rounded-t-md bg-white p-3.5 shadow-[0_10px_30px_-12px_rgba(0,0,0,0.3)]">
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

export function BusinessView() {
  const navigate = useNavigate()
  const takeover = useStore($terminalTakeover)
  const [question, setQuestion] = useState('')
  const canStartChat = !takeover

  const startChat = (prompt: string) => {
    if (!canStartChat) {
      return
    }

    queueComposerSeed(prompt)
    navigate(NEW_CHAT_ROUTE)
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden bg-background text-foreground pt-(--titlebar-height)">
      <div className="mx-auto w-full max-w-5xl px-8 pb-24 pt-6">
        {/* Header */}
        <header className="flex flex-wrap items-end gap-4">
          <div
            className="grid size-12 shrink-0 place-items-center rounded-2xl text-white shadow-lg"
            style={{ background: 'linear-gradient(145deg,#3D7BFF,#0038A8)', boxShadow: '0 10px 24px -10px rgba(0,83,253,.6)' }}
          >
            <Codicon name="briefcase" size="1.4rem" />
          </div>
          <div className="min-w-0 flex-1">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-2 py-1 text-[0.6875rem] font-semibold uppercase tracking-wide text-primary">
              Business documents
            </span>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">Business Hub</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Write, extract and review business documents with the assistant.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Each action opens a chat with a prompt you can edit. Nothing is sent until you send it.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-border bg-card px-3.5 text-[0.8125rem] font-semibold shadow-sm transition-colors hover:border-primary/40 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartChat}
              onClick={() => startChat(SCAN_TO_TEXT_PROMPT)}
              type="button"
            >
              <Codicon name="layers" size="0.9rem" />
              Scan to text
            </button>
            <button
              className="inline-flex h-9 items-center gap-2 rounded-xl px-3.5 text-[0.8125rem] font-semibold text-white shadow-sm transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartChat}
              onClick={() => startChat(NEW_DOCUMENT_PROMPT)}
              style={{ background: 'linear-gradient(180deg,#3D7BFF,#0053FD)' }}
              type="button"
            >
              <Codicon name="add" size="0.9rem" />
              New document
            </button>
          </div>
        </header>

        {takeover && (
          <p className="mt-4 rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground" role="status">
            Terminal takeover is on, so chats open in the terminal. Turn it off to start a chat from here.
          </p>
        )}

        {/* AI Consultant */}
        <form
          className="mt-6 flex items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-sm focus-within:ring-2 focus-within:ring-primary/40"
          onSubmit={event => {
            event.preventDefault()

            if (question.trim()) {
              startChat(question)
            }
          }}
        >
          <div
            className="grid size-9 shrink-0 place-items-center rounded-xl text-white"
            style={{ background: 'linear-gradient(145deg,#C98A2B,#8a5a12)' }}
          >
            <Codicon name="sparkle" size="1.05rem" />
          </div>
          <div className="min-w-0 flex-1">
            <label className="text-[0.8125rem] font-semibold" htmlFor="business-consultant">
              AI Consultant
            </label>
            <input
              className="w-full bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed"
              disabled={!canStartChat}
              id="business-consultant"
              onChange={event => setQuestion(event.target.value)}
              placeholder="Ask for guidance: “Make my CV stronger for a role in Douala”…"
              value={question}
            />
          </div>
          <button
            className="inline-flex h-8 items-center gap-2 rounded-lg px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canStartChat || !question.trim()}
            style={{ background: 'linear-gradient(180deg,#B57E23,#8a5a12)' }}
            type="submit"
          >
            Open in chat
          </button>
        </form>

        {/* Builder gallery */}
        <div className="mb-4 mt-9 flex items-center gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Interactive builders</h2>
          <span className="rounded-md bg-[#1F8A65]/12 px-2 py-1 text-[0.6875rem] font-semibold text-[#17694D]">
            Starts in chat
          </span>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {BUILDERS.map(b => (
            <button
              className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card text-left shadow-sm transition-all hover:-translate-y-1 hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 disabled:hover:shadow-sm"
              disabled={!canStartChat}
              key={b.id}
              onClick={() => startChat(BUILDER_PROMPTS[b.id])}
              type="button"
            >
              <div className="relative h-[150px] overflow-hidden bg-gradient-to-br from-primary/[0.08] to-transparent">
                <DocLines variant={b.id === 'invoice' ? 'invoice' : b.id === 'deck' ? 'deck' : 'cv'} />
              </div>
              <div className="flex items-start gap-2.5 p-3.5">
                <span
                  className={cn(
                    'grid size-8 shrink-0 place-items-center rounded-lg',
                    b.accent === 'gold' ? 'bg-[#C98A2B]/12 text-[#B57E23]' : 'bg-primary/10 text-primary'
                  )}
                >
                  <Codicon name={b.icon} size="1rem" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{b.title}</span>
                  <span className="mt-0.5 block text-[0.6875rem] text-muted-foreground">{b.sub}</span>
                </span>
                <Codicon className="mt-1 text-muted-foreground transition group-hover:translate-x-0.5" name="chevron-right" size="0.85rem" />
              </div>
            </button>
          ))}
        </div>

        {/* Scan to text CTA */}
        <button
          className="group relative mt-6 flex w-full items-center gap-6 overflow-hidden rounded-2xl px-7 py-6 text-left text-white disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!canStartChat}
          onClick={() => startChat(SCAN_TO_TEXT_PROMPT)}
          style={{ background: 'linear-gradient(135deg,#0b1020,#12224e 55%,#0a2f6b)' }}
          type="button"
        >
          <span
            className="pointer-events-none absolute inset-0"
            style={{ background: 'radial-gradient(50% 120% at 88% 10%,rgba(61,123,255,.5),transparent 55%)' }}
          />
          <span className="relative z-10 flex-1">
            <span className="inline-flex rounded-md bg-white/15 px-2 py-1 text-[0.6875rem] font-semibold uppercase tracking-wide">
              Quick start
            </span>
            <span className="mt-3 block text-xl font-semibold">Turn photos and PDFs into text</span>
            <span className="mt-2 block max-w-lg text-sm text-white/75">
              Attach photos or text PDFs. The assistant reads each file and extracts its text. Unclear text is marked,
              not guessed.
            </span>
          </span>
          <span className="relative z-10 hidden shrink-0 items-center gap-3 sm:flex">
            <span className="flex">
              {['#f2a65a', '#5a8cf2', '#57b98b'].map((c, i) => (
                <span
                  className="size-16 rounded-lg border-2 border-white/15 shadow-xl"
                  key={c}
                  style={{ background: `linear-gradient(150deg,${c},rgba(0,0,0,.35))`, marginLeft: i ? '-1.25rem' : 0, transform: `rotate(${(i - 1) * 8}deg)` }}
                />
              ))}
            </span>
            <Codicon name="arrow-right" size="1.4rem" />
            <span className="grid h-20 w-16 place-items-center gap-1 rounded-xl bg-white text-[#0a2f6b] shadow-xl">
              <Codicon name="file" size="1.5rem" />
              <b className="text-[0.625rem] font-bold">Text</b>
            </span>
          </span>
        </button>

        {/* Feature grid */}
        <h2 className="mb-4 mt-9 text-lg font-semibold tracking-tight">What the assistant does here</h2>
        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(f => (
            <div className="rounded-2xl border border-border bg-card p-4 shadow-sm" key={f.title}>
              <span
                className={cn(
                  'mb-3 grid size-9 place-items-center rounded-xl',
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

        <p className="mt-6 text-xs text-muted-foreground">
          Drafts can contain errors. Check amounts, dates, names and legal terms before you sign or send.
        </p>
      </div>
    </div>
  )
}
