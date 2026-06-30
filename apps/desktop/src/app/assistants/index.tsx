import { useStore } from '@nanostores/react'
import type * as React from 'react'
import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import {
  $assistants,
  ASSISTANT_COLORS,
  ASSISTANT_ICONS,
  colorFor,
  createAssistant,
  deleteAssistant,
  duplicateAssistant,
  type AssistantConfig,
  updateAssistant
} from '@/store/assistants'

import { PageSearchShell } from '../page-search-shell'
import { NEW_CHAT_ROUTE } from '../routes'
import type { SetStatusbarItemGroup } from '../shell/statusbar-controls'

const STARTER_TEMPLATES: Omit<AssistantConfig, 'id' | 'createdAt' | 'updatedAt'>[] = [
  {
    name: 'Marketing Assistant',
    description: 'Crafts compelling copy, campaigns, and brand messaging.',
    icon: '📢',
    color: 'purple',
    systemPrompt:
      'You are an expert marketing assistant. Help create compelling copy, develop campaigns, suggest strategies, and craft brand messaging that resonates with target audiences. Always ask about the target audience and goals before proposing solutions.',
    model: '',
    provider: '',
    temperature: 0.8
  },
  {
    name: 'Sales Agent',
    description: 'Helps qualify leads, craft pitches, and close deals.',
    icon: '💼',
    color: 'blue',
    systemPrompt:
      'You are a skilled sales assistant. Help qualify prospects, create persuasive pitches, handle objections, draft proposals, and develop follow-up strategies. Focus on value-based selling and building genuine relationships.',
    model: '',
    provider: '',
    temperature: 0.7
  },
  {
    name: 'Legal Assistant',
    description: 'Reviews documents, drafts letters, and explains legal concepts.',
    icon: '⚖️',
    color: 'slate',
    systemPrompt:
      'You are a knowledgeable legal assistant. Help review contracts, draft formal letters, explain legal concepts in plain language, and identify potential issues. Always remind the user to consult a qualified lawyer for binding legal advice.',
    model: '',
    provider: '',
    temperature: 0.3
  },
  {
    name: 'Software Architect',
    description: 'Designs systems, reviews code, and guides technical decisions.',
    icon: '🏗️',
    color: 'teal',
    systemPrompt:
      'You are a senior software architect. Help design scalable systems, review architecture decisions, recommend patterns and best practices, analyze tradeoffs, and guide technical strategy. Ask about constraints, scale requirements, and team expertise before proposing solutions.',
    model: '',
    provider: '',
    temperature: 0.4
  },
  {
    name: 'Startup Advisor',
    description: 'Guides founders through strategy, fundraising, and growth.',
    icon: '💡',
    color: 'amber',
    systemPrompt:
      'You are an experienced startup advisor. Help with business strategy, product-market fit, fundraising preparation, pitch decks, growth tactics, and building the right team. Ground advice in real-world startup experience and be direct about hard truths.',
    model: '',
    provider: '',
    temperature: 0.7
  },
  {
    name: 'HR Recruiter',
    description: 'Writes job descriptions, screens candidates, and drafts offers.',
    icon: '🎯',
    color: 'rose',
    systemPrompt:
      'You are a professional HR recruiter. Help write compelling job descriptions, develop interview questions, evaluate candidates fairly, draft offer letters, and create onboarding plans. Focus on inclusive language and objective evaluation criteria.',
    model: '',
    provider: '',
    temperature: 0.5
  }
]

interface AssistantsViewProps extends React.ComponentProps<'section'> {
  setStatusbarItemGroup?: SetStatusbarItemGroup
}

export function AssistantsView({ setStatusbarItemGroup: _unused, ...props }: AssistantsViewProps) {
  const navigate = useNavigate()
  const assistants = useStore($assistants)
  const [query, setQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return assistants
    return assistants.filter(
      a =>
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q)
    )
  }, [assistants, query])

  const handleStartChat = useCallback(
    (assistant: AssistantConfig) => {
      // Store the assistant context so the chat session can pick it up
      try {
        window.sessionStorage.setItem(
          'tchuekam.pending-assistant',
          JSON.stringify({ systemPrompt: assistant.systemPrompt, name: assistant.name, model: assistant.model, provider: assistant.provider })
        )
      } catch {
        // Best-effort
      }
      navigate(NEW_CHAT_ROUTE)
    },
    [navigate]
  )

  const handleDelete = useCallback((id: string, name: string) => {
    if (window.confirm(`Delete "${name}"? This cannot be undone.`)) {
      deleteAssistant(id)
    }
  }, [])

  const editingAssistant = editingId ? assistants.find(a => a.id === editingId) : null

  return (
    <PageSearchShell
      {...props}
      onSearchChange={setQuery}
      searchPlaceholder="Search assistants…"
      searchTrailingAction={
        <Button
          aria-label="Create assistant"
          className="text-(--ui-text-tertiary) hover:bg-transparent hover:text-foreground"
          onClick={() => setCreating(true)}
          size="icon-xs"
          title="Create assistant"
          type="button"
          variant="ghost"
        >
          <Codicon name="add" size="0.875rem" />
        </Button>
      }
      searchValue={query}
    >
      <div className="h-full overflow-y-auto px-4 py-3">
        {assistants.length === 0 ? (
          <EmptyState onAddTemplate={() => setShowTemplates(true)} onCreate={() => setCreating(true)} />
        ) : filtered.length === 0 ? (
          <div className="grid min-h-52 place-items-center text-center">
            <div>
              <div className="text-sm font-medium">No assistants match</div>
              <div className="mt-1 text-xs text-muted-foreground">Try a broader search.</div>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{filtered.length} assistant{filtered.length !== 1 ? 's' : ''}</span>
              <Button
                className="h-6 gap-1 text-xs"
                onClick={() => setShowTemplates(true)}
                size="sm"
                type="button"
                variant="ghost"
              >
                <Codicon name="library" size="0.75rem" />
                Templates
              </Button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map(assistant => (
                <AssistantCard
                  assistant={assistant}
                  key={assistant.id}
                  onDelete={() => handleDelete(assistant.id, assistant.name)}
                  onDuplicate={() => duplicateAssistant(assistant.id)}
                  onEdit={() => setEditingId(assistant.id)}
                  onStartChat={() => handleStartChat(assistant)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Create / Edit dialog */}
      <AssistantDialog
        assistant={editingAssistant ?? undefined}
        onClose={() => {
          setCreating(false)
          setEditingId(null)
        }}
        onSave={config => {
          if (editingId) {
            updateAssistant(editingId, config)
            setEditingId(null)
          } else {
            createAssistant(config)
            setCreating(false)
          }
        }}
        open={creating || editingId !== null}
      />

      {/* Templates dialog */}
      <TemplatesDialog
        onClose={() => setShowTemplates(false)}
        onSelect={template => {
          createAssistant(template)
          setShowTemplates(false)
        }}
        open={showTemplates}
      />
    </PageSearchShell>
  )
}

// ─── Assistant Card ────────────────────────────────────────────────────────────

interface AssistantCardProps {
  assistant: AssistantConfig
  onStartChat: () => void
  onEdit: () => void
  onDuplicate: () => void
  onDelete: () => void
}

function AssistantCard({ assistant, onStartChat, onEdit, onDuplicate, onDelete }: AssistantCardProps) {
  const color = colorFor(assistant.color)
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <article
      className="group/card relative flex flex-col overflow-hidden rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-chat-bubble-background) p-4 shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <div
          className={cn(
            'grid size-10 shrink-0 place-items-center rounded-xl text-xl ring-1',
            color.bg,
            color.ring
          )}
        >
          {assistant.icon}
        </div>
        <div className="relative ml-auto">
          <Button
            aria-label="More options"
            className={cn(
              'size-6 text-(--ui-text-tertiary) opacity-0 transition-opacity hover:text-foreground group-hover/card:opacity-100',
              menuOpen && 'opacity-100'
            )}
            onClick={() => setMenuOpen(v => !v)}
            size="icon-xs"
            type="button"
            variant="ghost"
          >
            <Codicon name="ellipsis" size="0.875rem" />
          </Button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 top-7 z-50 min-w-32 overflow-hidden rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-chat-surface-background) shadow-lg">
                {[
                  { label: 'Edit', icon: 'edit', action: onEdit },
                  { label: 'Duplicate', icon: 'copy', action: onDuplicate },
                  { label: 'Delete', icon: 'trash', action: onDelete, danger: true }
                ].map(item => (
                  <button
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-(--ui-control-hover-background)',
                      item.danger ? 'text-red-500 hover:text-red-600' : 'text-(--ui-text-secondary) hover:text-foreground'
                    )}
                    key={item.label}
                    onClick={() => { setMenuOpen(false); item.action() }}
                    type="button"
                  >
                    <Codicon name={item.icon as any} size="0.75rem" />
                    {item.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="min-w-0 flex-1 space-y-1">
        <h3 className="truncate text-sm font-semibold leading-tight">{assistant.name}</h3>
        <p className="line-clamp-2 text-xs text-muted-foreground">{assistant.description || 'No description.'}</p>
      </div>

      {assistant.model && (
        <div className="mt-2">
          <span className="rounded-md bg-(--ui-bg-quinary) px-1.5 py-0.5 font-mono text-[0.65rem] text-(--ui-text-tertiary)">
            {assistant.model}
          </span>
        </div>
      )}

      <div className="mt-3 flex gap-1.5">
        <Button
          className="h-7 flex-1 gap-1.5 text-xs"
          onClick={onStartChat}
          size="sm"
          type="button"
          variant="default"
        >
          <Codicon name="comment" size="0.75rem" />
          Start chat
        </Button>
        <Button
          className="h-7"
          onClick={onEdit}
          size="icon-xs"
          title="Edit assistant"
          type="button"
          variant="outline"
        >
          <Codicon name="edit" size="0.75rem" />
        </Button>
      </div>
    </article>
  )
}

// ─── Create / Edit Dialog ─────────────────────────────────────────────────────

interface AssistantDialogProps {
  open: boolean
  assistant?: AssistantConfig
  onClose: () => void
  onSave: (config: Omit<AssistantConfig, 'id' | 'createdAt' | 'updatedAt'>) => void
}

function AssistantDialog({ open, assistant, onClose, onSave }: AssistantDialogProps) {
  const [name, setName] = useState(assistant?.name ?? '')
  const [description, setDescription] = useState(assistant?.description ?? '')
  const [icon, setIcon] = useState(assistant?.icon ?? '🤖')
  const [color, setColor] = useState(assistant?.color ?? 'blue')
  const [systemPrompt, setSystemPrompt] = useState(assistant?.systemPrompt ?? '')
  const [model, setModel] = useState(assistant?.model ?? '')
  const [temperature, setTemperature] = useState(assistant?.temperature ?? 0.7)

  // Reset when assistant prop changes
  const prevAssistant = assistant
  if (prevAssistant?.id !== assistant?.id) {
    setName(assistant?.name ?? '')
    setDescription(assistant?.description ?? '')
    setIcon(assistant?.icon ?? '🤖')
    setColor(assistant?.color ?? 'blue')
    setSystemPrompt(assistant?.systemPrompt ?? '')
    setModel(assistant?.model ?? '')
    setTemperature(assistant?.temperature ?? 0.7)
  }

  const canSave = name.trim().length > 0

  function handleSave() {
    if (!canSave) return
    onSave({ name: name.trim(), description: description.trim(), icon, color, systemPrompt: systemPrompt.trim(), model: model.trim(), provider: assistant?.provider ?? '', temperature })
  }

  return (
    <Dialog onOpenChange={open => !open && onClose()} open={open}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{assistant ? 'Edit assistant' : 'Create assistant'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Icon + color row */}
          <div className="flex items-start gap-3">
            <div className="shrink-0">
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">Icon</div>
              <div className="flex flex-wrap gap-1.5">
                {ASSISTANT_ICONS.map(ic => (
                  <button
                    className={cn(
                      'grid size-8 cursor-pointer place-items-center rounded-lg text-base transition-all hover:scale-110',
                      icon === ic ? 'ring-2 ring-blue-500' : 'opacity-60 hover:opacity-100'
                    )}
                    key={ic}
                    onClick={() => setIcon(ic)}
                    type="button"
                  >
                    {ic}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1">
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">Color</div>
              <div className="flex flex-wrap gap-1.5">
                {ASSISTANT_COLORS.map(c => (
                  <button
                    className={cn(
                      'size-6 cursor-pointer rounded-full transition-all hover:scale-110',
                      c.bg,
                      color === c.value ? 'ring-2 ring-offset-2 ring-current' : ''
                    )}
                    key={c.value}
                    onClick={() => setColor(c.value)}
                    title={c.label}
                    type="button"
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Name */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="asst-name">Name *</label>
            <Input
              id="asst-name"
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Marketing Assistant"
              value={name}
            />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="asst-desc">Description</label>
            <Input
              id="asst-desc"
              onChange={e => setDescription(e.target.value)}
              placeholder="Short description of what this assistant does"
              value={description}
            />
          </div>

          {/* System prompt */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="asst-prompt">
              System prompt
            </label>
            <Textarea
              className="min-h-32 font-mono text-xs"
              id="asst-prompt"
              onChange={e => setSystemPrompt(e.target.value)}
              placeholder="You are a helpful assistant specialized in…"
              value={systemPrompt}
            />
          </div>

          {/* Model */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="asst-model">
              Preferred model <span className="font-normal opacity-60">(optional — leave blank to use global setting)</span>
            </label>
            <Input
              id="asst-model"
              onChange={e => setModel(e.target.value)}
              placeholder="e.g. claude-sonnet-4-6"
              value={model}
            />
          </div>

          {/* Temperature */}
          <div className="space-y-1.5">
            <label className="flex items-center justify-between text-xs font-medium text-muted-foreground" htmlFor="asst-temp">
              <span>Temperature</span>
              <span className="font-mono">{temperature.toFixed(1)}</span>
            </label>
            <input
              className="w-full cursor-pointer accent-blue-500"
              id="asst-temp"
              max={1}
              min={0}
              onChange={e => setTemperature(Number(e.target.value))}
              step={0.1}
              type="range"
              value={temperature}
            />
            <div className="flex justify-between text-[0.62rem] text-muted-foreground">
              <span>Precise</span><span>Balanced</span><span>Creative</span>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={onClose} type="button" variant="ghost">Cancel</Button>
          <Button disabled={!canSave} onClick={handleSave} type="button">
            {assistant ? 'Save changes' : 'Create assistant'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Templates Dialog ─────────────────────────────────────────────────────────

interface TemplatesDialogProps {
  open: boolean
  onClose: () => void
  onSelect: (template: Omit<AssistantConfig, 'id' | 'createdAt' | 'updatedAt'>) => void
}

function TemplatesDialog({ open, onClose, onSelect }: TemplatesDialogProps) {
  return (
    <Dialog onOpenChange={open => !open && onClose()} open={open}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Starter templates</DialogTitle>
        </DialogHeader>
        <div className="grid gap-2 py-2 sm:grid-cols-2">
          {STARTER_TEMPLATES.map(template => {
            const color = colorFor(template.color)
            return (
              <button
                className="flex cursor-pointer items-start gap-3 rounded-xl border border-(--ui-stroke-tertiary) p-3 text-left transition-colors hover:bg-(--ui-control-hover-background)"
                key={template.name}
                onClick={() => onSelect(template)}
                type="button"
              >
                <div className={cn('grid size-9 shrink-0 place-items-center rounded-lg text-lg ring-1', color.bg, color.ring)}>
                  {template.icon}
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{template.name}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{template.description}</div>
                </div>
              </button>
            )
          })}
        </div>
        <DialogFooter>
          <Button onClick={onClose} type="button" variant="ghost">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Empty State ──────────────────────────────────────────────────────────────

function EmptyState({ onCreate, onAddTemplate }: { onCreate: () => void; onAddTemplate: () => void }) {
  return (
    <div className="grid min-h-[60vh] place-items-center text-center">
      <div className="max-w-sm space-y-4">
        <div className="mx-auto grid size-16 place-items-center rounded-2xl bg-(--ui-bg-quinary) text-3xl">🤖</div>
        <div>
          <h2 className="text-base font-semibold">No assistants yet</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Create a persistent AI assistant with a custom persona, system prompt, and preferred model.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <Button className="gap-2" onClick={onAddTemplate} type="button" variant="default">
            <Codicon name="library" size="0.875rem" />
            Browse templates
          </Button>
          <Button className="gap-2" onClick={onCreate} type="button" variant="outline">
            <Codicon name="add" size="0.875rem" />
            Create from scratch
          </Button>
        </div>
      </div>
    </div>
  )
}
