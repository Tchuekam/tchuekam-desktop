// @vitest-environment node
import '../../business/test-dom-setup'

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SidebarProvider } from '@/components/ui/sidebar'
import { $sidebarOpen, setSidebarOpen } from '@/store/layout'

import { ChatSidebar } from './index'

vi.mock('@/hermes', () => ({
  searchSessions: vi.fn().mockResolvedValue({ results: [] })
}))

describe('ChatSidebar mobile visibility', () => {
  beforeEach(() => {
    setSidebarOpen(true)
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn()
      }))
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders all navigation labels without hiding them on mobile screens', () => {
    render(
      <SidebarProvider open>
        <ChatSidebar
          currentView="chat"
          onArchiveSession={vi.fn()}
          onDeleteSession={vi.fn()}
          onLoadMoreSessions={vi.fn()}
          onNavigate={vi.fn()}
          onNewSessionInWorkspace={vi.fn()}
          onResumeSession={vi.fn()}
        />
      </SidebarProvider>
    )

    for (const label of [
      'New session',
      'Business Hub',
      'Mobile App',
      'Image Studio',
      'Skills & Tools',
      'AI Agents',
      'Artifacts'
    ]) {
      const textNode = screen.getByText(label)
      expect(textNode).toBeTruthy()
      expect(textNode.className).not.toContain('max-[46.25rem]:hidden')
      expect(textNode.className).not.toContain('hidden sm:')
    }

    const newBadge = screen.getByText('NEW')
    expect(newBadge).toBeTruthy()
    expect(newBadge.className).not.toContain('max-[46.25rem]:hidden')

    fireEvent.click(screen.getByText('Business Hub'))
    expect($sidebarOpen.get()).toBe(false)
  })
})
