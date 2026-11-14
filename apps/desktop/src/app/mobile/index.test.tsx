// @vitest-environment node
import '../business/test-dom-setup'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { MobileView } from './mobile-view'
import { MobilePromoBanner } from './mobile-banner'

// Mock haptics
vi.mock('@/lib/haptics', () => ({
  triggerHaptic: vi.fn()
}))

describe('MobileView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders the header, badge, and primary 1-click APK download button', () => {
    render(
      <MemoryRouter>
        <MobileView />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { name: 'TchueKAM Mobile' })).toBeTruthy()
    expect(screen.getByText('v1.0.0 MOBILE RELEASE')).toBeTruthy()

    // 1-Click Android APK Download button
    const apkButton = screen.getByRole('link', { name: /Download Android APK \(1-Click\)/i })
    expect(apkButton).toBeTruthy()
    expect(apkButton.getAttribute('href')).toBe('/api/download/android')
    expect(apkButton.getAttribute('download')).toBe('TchueKAM-Mobile.apk')
  })

  it('renders the iOS & Web PWA card with copy link functionality', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock
      }
    })

    render(
      <MemoryRouter>
        <MobileView />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { name: 'iOS & Web (PWA)' })).toBeTruthy()
    const copyBtn = screen.getByRole('button', { name: /Copy Mobile Link/i })
    expect(copyBtn).toBeTruthy()

    fireEvent.click(copyBtn)
    expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining('/mobile'))
  })

  it('renders interactive phone simulator and switches scenarios', () => {
    render(
      <MemoryRouter>
        <MobileView />
      </MemoryRouter>
    )

    expect(screen.getByText('What are you deciding right now?')).toBeTruthy()
    expect(screen.getByText('Executive VP Hire')).toBeTruthy()

    // Click on another scenario
    const pricingBtn = screen.getByRole('button', { name: /Tiered Pricing Restructure/i })
    fireEvent.click(pricingBtn)

    expect(screen.getByText(/Yang Fire day promotes assertive value capture/i)).toBeTruthy()
  })

  it('executes a scenario in the mobile simulator', async () => {
    render(
      <MemoryRouter>
        <MobileView />
      </MemoryRouter>
    )

    const executeBtn = screen.getByRole('button', { name: /Execute Scenario →/i })
    fireEvent.click(executeBtn)

    await waitFor(
      () => {
        expect(screen.getByText(/Action Plan:/i)).toBeTruthy()
      },
      { timeout: 3500 }
    )
  })

  it('switches between simulator tabs (Decide, Chat, Tools)', () => {
    render(
      <MemoryRouter>
        <MobileView />
      </MemoryRouter>
    )

    // Switch to Chat tab
    const chatTab = screen.getByRole('button', { name: /Chat/i })
    fireEvent.click(chatTab)
    expect(screen.getByText(/TchueKAM Mobile Agent:/i)).toBeTruthy()

    // Switch to Tools tab
    const toolsTab = screen.getByRole('button', { name: /Tools/i })
    fireEvent.click(toolsTab)
    expect(screen.getByText(/Installed Mobile Capabilities/i)).toBeTruthy()
    expect(screen.getByText(/Document Scanner/i)).toBeTruthy()
  })
})

describe('MobilePromoBanner', () => {
  beforeEach(() => {
    sessionStorage.clear()
    window.innerWidth = 500
  })

  afterEach(() => {
    cleanup()
  })

  it('renders on mobile screen and can be dismissed', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <MobilePromoBanner />
      </MemoryRouter>
    )

    expect(screen.getByText(/TchueKAM Mobile is out!/i)).toBeTruthy()
    const dismissBtn = screen.getByRole('button', { name: /Dismiss banner/i })
    fireEvent.click(dismissBtn)

    expect(screen.queryByText(/TchueKAM Mobile is out!/i)).toBeNull()
  })
})
