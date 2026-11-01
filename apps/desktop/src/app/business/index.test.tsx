import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type * as ReactRouter from 'react-router-dom'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $terminalTakeover, setTerminalTakeover } from '@/app/right-sidebar/store'
import { $pendingComposerSeed } from '@/store/composer'

import { NEW_CHAT_ROUTE } from '../routes'

import { BUILDER_PROMPTS, type BuilderId, NEW_DOCUMENT_PROMPT, SCAN_TO_TEXT_PROMPT } from './prompts'

import { BusinessView } from './index'

const navigate = vi.fn()
const seedsSeenAtNavigate: Array<string | null> = []

vi.mock('react-router-dom', async importOriginal => ({
  ...(await importOriginal<typeof ReactRouter>()),
  useNavigate: () => navigate
}))

// Typed as a full record so adding a builder without a row here fails type-checking.
const BUILDER_TITLES: Record<BuilderId, string> = {
  cv: 'CV / Résumé',
  invoice: 'Facture',
  contract: 'Contrat',
  deck: 'Pitch Deck',
  plan: 'Business Plan',
  quote: 'Devis',
  letter: 'Lettre de motivation',
  attestation: 'Attestation'
}

function renderView() {
  return render(
    <MemoryRouter>
      <BusinessView />
    </MemoryRouter>
  )
}

function consultantInput() {
  return screen.getByLabelText<HTMLInputElement>('AI Consultant')
}

function openInChatButton() {
  return screen.getByRole<HTMLButtonElement>('button', { name: 'Open in chat' })
}

beforeEach(() => {
  navigate.mockReset()
  seedsSeenAtNavigate.length = 0
  $pendingComposerSeed.set(null)
  setTerminalTakeover(false)
  // Record the queued seed at the moment of navigation: the composer reads it
  // on mount, so it must already be set when the route changes.
  navigate.mockImplementation(() => seedsSeenAtNavigate.push($pendingComposerSeed.get()))
})

afterEach(() => {
  cleanup()
  setTerminalTakeover(false)
})

describe('BusinessView actions', () => {
  it.each(Object.entries(BUILDER_TITLES) as Array<[BuilderId, string]>)(
    '%s builder queues its prompt and opens a new chat',
    (id, title) => {
      renderView()

      fireEvent.click(screen.getByRole('button', { name: new RegExp(title) }))

      expect(seedsSeenAtNavigate).toEqual([BUILDER_PROMPTS[id]])
      expect(navigate).toHaveBeenCalledWith(NEW_CHAT_ROUTE)
    }
  )

  it.each([
    ['header Scan to text', /^Scan to text$/, SCAN_TO_TEXT_PROMPT],
    ['header New document', /^New document$/, NEW_DOCUMENT_PROMPT],
    ['scan banner', /Turn photos and PDFs into text/, SCAN_TO_TEXT_PROMPT]
  ])('%s queues its prompt and opens a new chat', (_label, name, prompt) => {
    renderView()

    fireEvent.click(screen.getByRole('button', { name }))

    expect(seedsSeenAtNavigate).toEqual([prompt])
    expect(navigate).toHaveBeenCalledWith(NEW_CHAT_ROUTE)
  })
})

describe('BusinessView AI Consultant', () => {
  it('disables Open in chat until there is text', () => {
    renderView()

    expect(openInChatButton().disabled).toBe(true)

    fireEvent.change(consultantInput(), { target: { value: 'Make my CV stronger' } })

    expect(consultantInput().value).toBe('Make my CV stronger')
    expect(openInChatButton().disabled).toBe(false)
  })

  it('keeps Open in chat disabled for whitespace-only input', () => {
    renderView()

    fireEvent.change(consultantInput(), { target: { value: '   ' } })

    expect(openInChatButton().disabled).toBe(true)
  })

  it('queues the trimmed question on submit and does not send it', () => {
    renderView()

    fireEvent.change(consultantInput(), { target: { value: '  Make my CV stronger  ' } })
    fireEvent.click(openInChatButton())

    expect(seedsSeenAtNavigate).toEqual(['Make my CV stronger'])
    expect(navigate).toHaveBeenCalledWith(NEW_CHAT_ROUTE)
  })

  it('cancels the native form submission so the page never reloads', () => {
    renderView()

    fireEvent.change(consultantInput(), { target: { value: 'Make my CV stronger' } })

    const form = consultantInput().closest('form') as HTMLFormElement

    expect(fireEvent.submit(form)).toBe(false)
  })

  it('does nothing when the question is blank', () => {
    renderView()

    fireEvent.change(consultantInput(), { target: { value: '   ' } })
    fireEvent.submit(consultantInput().closest('form') as HTMLFormElement)

    expect(navigate).not.toHaveBeenCalled()
    expect($pendingComposerSeed.get()).toBeNull()
  })
})

describe('BusinessView with terminal takeover on', () => {
  it('disables every action and says why, so no prompt can wait for a chat that never opens', () => {
    setTerminalTakeover(true)
    renderView()

    expect(screen.getByRole('status').textContent).toContain('Terminal takeover is on')
    expect(screen.getByRole('button', { name: /^Scan to text$/ }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: /^New document$/ }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: /CV \/ Résumé/ }).hasAttribute('disabled')).toBe(true)
    expect(openInChatButton().disabled).toBe(true)
  })

  it('queues nothing when a disabled action is somehow triggered', () => {
    setTerminalTakeover(true)
    renderView()

    fireEvent.click(screen.getByRole('button', { name: /CV \/ Résumé/ }))

    expect(navigate).not.toHaveBeenCalled()
    expect($pendingComposerSeed.get()).toBeNull()
    expect($terminalTakeover.get()).toBe(true)
  })
})
