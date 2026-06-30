import { atom } from 'nanostores'

export interface AssistantConfig {
  id: string
  name: string
  description: string
  icon: string
  color: string
  systemPrompt: string
  model: string
  provider: string
  temperature: number
  createdAt: number
  updatedAt: number
}

const STORAGE_KEY = 'tchuekam.project-assistants'

function loadAssistants(): AssistantConfig[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveAssistants(list: AssistantConfig[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch {
    // Best-effort
  }
}

export const $assistants = atom<AssistantConfig[]>(loadAssistants())

export function createAssistant(config: Omit<AssistantConfig, 'id' | 'createdAt' | 'updatedAt'>): AssistantConfig {
  const now = Date.now()
  const assistant: AssistantConfig = {
    ...config,
    id: `asst_${now}_${Math.random().toString(36).slice(2, 8)}`,
    createdAt: now,
    updatedAt: now
  }
  const next = [...$assistants.get(), assistant]
  $assistants.set(next)
  saveAssistants(next)
  return assistant
}

export function updateAssistant(id: string, patch: Partial<Omit<AssistantConfig, 'id' | 'createdAt'>>): void {
  const next = $assistants.get().map(a =>
    a.id === id ? { ...a, ...patch, updatedAt: Date.now() } : a
  )
  $assistants.set(next)
  saveAssistants(next)
}

export function deleteAssistant(id: string): void {
  const next = $assistants.get().filter(a => a.id !== id)
  $assistants.set(next)
  saveAssistants(next)
}

export function duplicateAssistant(id: string): AssistantConfig | null {
  const source = $assistants.get().find(a => a.id === id)
  if (!source) return null
  return createAssistant({
    ...source,
    name: `${source.name} (copy)`
  })
}

export const ASSISTANT_ICONS = ['🤖', '💼', '⚖️', '🏗️', '📢', '💡', '🔬', '💻', '🎨', '📊', '🌐', '🛡️', '🎯', '✍️', '🗂️']
export const ASSISTANT_COLORS = [
  { label: 'Blue', value: 'blue', bg: 'bg-blue-500/10', ring: 'ring-blue-500/20', text: 'text-blue-600 dark:text-blue-400' },
  { label: 'Purple', value: 'purple', bg: 'bg-purple-500/10', ring: 'ring-purple-500/20', text: 'text-purple-600 dark:text-purple-400' },
  { label: 'Green', value: 'green', bg: 'bg-green-500/10', ring: 'ring-green-500/20', text: 'text-green-600 dark:text-green-400' },
  { label: 'Orange', value: 'orange', bg: 'bg-orange-500/10', ring: 'ring-orange-500/20', text: 'text-orange-600 dark:text-orange-400' },
  { label: 'Rose', value: 'rose', bg: 'bg-rose-500/10', ring: 'ring-rose-500/20', text: 'text-rose-600 dark:text-rose-400' },
  { label: 'Teal', value: 'teal', bg: 'bg-teal-500/10', ring: 'ring-teal-500/20', text: 'text-teal-600 dark:text-teal-400' },
  { label: 'Amber', value: 'amber', bg: 'bg-amber-500/10', ring: 'ring-amber-500/20', text: 'text-amber-600 dark:text-amber-400' },
  { label: 'Slate', value: 'slate', bg: 'bg-slate-500/10', ring: 'ring-slate-500/20', text: 'text-slate-600 dark:text-slate-400' }
] as const

export type AssistantColor = (typeof ASSISTANT_COLORS)[number]

export function colorFor(value: string): AssistantColor {
  return ASSISTANT_COLORS.find(c => c.value === value) ?? ASSISTANT_COLORS[0]
}
