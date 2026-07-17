import { IconBolt, IconBooks, IconChartBar, IconSparkles } from '@tabler/icons-react'
import { useState } from 'react'

import { requestComposerFocus, requestComposerInsert } from '@/app/chat/composer/focus'

import introCopyJsonl from './intro-copy.jsonl?raw'

type IntroCopy = {
  headline: string
  body: string
}

/**
 * First-run affordances. The empty state has to teach what an AI OS for
 * business is *for* — a bare sentence leaves the operator guessing. Each card
 * seeds the composer through the external-insert bus rather than sending, so
 * the prompt stays editable before it runs.
 */
const STARTERS: ReadonlyArray<{ icon: typeof IconChartBar; label: string; prompt: string }> = [
  {
    icon: IconChartBar,
    label: 'Review business performance',
    prompt: 'Summarise how the business performed last month and flag anything that needs my attention.'
  },
  {
    icon: IconSparkles,
    label: 'Draft a marketing campaign',
    prompt: 'Draft a marketing campaign for our next launch — audience, channels, messaging, and a rough timeline.'
  },
  {
    icon: IconBolt,
    label: 'Automate a routine workflow',
    prompt: 'Help me automate a recurring workflow. Ask me what it involves, then propose the steps.'
  },
  {
    icon: IconBooks,
    label: 'Ask across your knowledge',
    prompt: 'Search everything we know and answer a question about our business.'
  }
]

function StarterCard({ icon: Icon, label, prompt }: (typeof STARTERS)[number]) {
  return (
    <button
      className="group flex h-full cursor-pointer flex-col items-start gap-2 rounded-lg border border-border bg-card p-3 text-left transition-colors duration-150 ease-out hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
      onClick={() => {
        requestComposerInsert(prompt, { mode: 'inline', target: 'main' })
        requestComposerFocus('main')
      }}
      type="button"
    >
      <Icon className="size-4 shrink-0 text-muted-foreground transition-colors duration-150 group-hover:text-foreground" stroke={1.5} />
      <span className="text-[0.8125rem] font-normal leading-snug text-foreground">{label}</span>
    </button>
  )
}

type IntroCopyRecord = IntroCopy & {
  personality: string
}

export type IntroProps = {
  personality?: string
  seed?: number
}

const NEUTRAL_PERSONALITIES = new Set(['', 'default', 'none', 'neutral'])

const FALLBACK_COPY: IntroCopy[] = [
  {
    headline: 'What can I help you run today?',
    body: "Bring a goal, a question, or a rough idea. I'll turn it into the next concrete step."
  },
  {
    headline: "What's on your mind?",
    body: "Share the context you have and I'll help you make sense of it before anything moves."
  },
  {
    headline: 'Where should we start?',
    body: "Give me the problem or the outcome you want. I'll keep the next step concrete."
  },
  {
    headline: 'What needs attention?',
    body: "Send it over — a campaign, a number that looks off, a process that keeps eating your week."
  },
  {
    headline: 'What are we moving today?',
    body: "Describe the work and I'll pull in the right skills, agents, and knowledge to get it done."
  }
]

function normalizeKey(value?: string): string {
  return (value || '').trim().toLowerCase()
}

function titleize(value: string): string {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function isIntroCopyRecord(value: unknown): value is IntroCopyRecord {
  if (!value || typeof value !== 'object') {
    return false
  }

  const record = value as Record<string, unknown>

  return (
    typeof record.personality === 'string' &&
    typeof record.headline === 'string' &&
    typeof record.body === 'string' &&
    Boolean(record.personality.trim()) &&
    Boolean(record.headline.trim()) &&
    Boolean(record.body.trim())
  )
}

function parseIntroCopy(raw: string): Record<string, IntroCopy[]> {
  const byPersonality: Record<string, IntroCopy[]> = {}

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()

    if (!trimmed) {
      continue
    }

    try {
      const parsed: unknown = JSON.parse(trimmed)

      if (!isIntroCopyRecord(parsed)) {
        continue
      }

      const key = normalizeKey(parsed.personality)
      byPersonality[key] ??= []
      byPersonality[key].push({
        headline: parsed.headline.trim(),
        body: parsed.body.trim()
      })
    } catch {
      // Bad generated copy should not break the whole desktop app.
    }
  }

  return byPersonality
}

const INTRO_COPY_BY_PERSONALITY = parseIntroCopy(introCopyJsonl)

function neutralCopy(): IntroCopy[] {
  return INTRO_COPY_BY_PERSONALITY.none || INTRO_COPY_BY_PERSONALITY.default || FALLBACK_COPY
}

function fallbackCopyForPersonality(personalityKey: string): IntroCopy[] {
  if (NEUTRAL_PERSONALITIES.has(personalityKey)) {
    return neutralCopy()
  }

  const label = titleize(personalityKey)

  return [
    {
      headline: `${label} mode is on. What should we work on?`,
      body: "Send the goal, question, or rough idea. I'll use your configured voice."
    },
    {
      headline: `What does ${label} TchuekaM need to see?`,
      body: "Bring the context or the stuck part. I'll adapt to your configured personality."
    },
    {
      headline: `${label} mode is ready.`,
      body: "Send the problem or the idea. I'll follow the personality you've configured."
    },
    {
      headline: `What should ${label} TchuekaM tackle?`,
      body: "Drop the work here and I'll keep the next step concrete."
    },
    {
      headline: 'Where should we begin?',
      body: `Give me the context and I'll answer in ${label} mode.`
    }
  ]
}

function pickCopy(copies: IntroCopy[], seed = 0): IntroCopy {
  return copies[Math.abs(seed) % copies.length] || FALLBACK_COPY[0]
}

function resolveCopy(personality?: string, seed?: number): IntroCopy {
  const personalityKey = normalizeKey(personality)

  const copies = NEUTRAL_PERSONALITIES.has(personalityKey)
    ? INTRO_COPY_BY_PERSONALITY[personalityKey] || neutralCopy()
    : INTRO_COPY_BY_PERSONALITY[personalityKey] || fallbackCopyForPersonality(personalityKey)

  return pickCopy(copies, seed)
}

export function Intro({ personality, seed }: IntroProps) {
  const [mountSeed] = useState(() => Math.floor(Math.random() * 100000))
  const copy = resolveCopy(personality, mountSeed + (seed ?? 0))

  return (
    <div
      className="flex w-full min-w-0 flex-col items-center justify-center px-6 py-8 lg:px-8"
      data-slot="aui_intro"
    >
      <div className="w-full min-w-0 max-w-2xl">
        <h1 className="m-0 text-center text-[2rem] font-medium leading-tight tracking-tight text-foreground">
          {copy.headline}
        </h1>

        <p className="mx-auto mt-3 max-w-lg text-center text-sm leading-relaxed text-muted-foreground">{copy.body}</p>

        <div className="mt-8 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {STARTERS.map(starter => (
            <StarterCard key={starter.label} {...starter} />
          ))}
        </div>
      </div>
    </div>
  )
}
