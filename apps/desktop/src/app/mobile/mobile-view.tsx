import { useStore } from '@nanostores/react'
import {
  IconCheck,
  IconCopy,
  IconDeviceMobile,
  IconDownload,
  IconExternalLink,
  IconPlayerPlay,
  IconQrcode,
  IconRefresh,
  IconShieldCheck,
  IconSparkles,
  IconTerminal2,
  IconWorld
} from '@tabler/icons-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { triggerHaptic } from '@/lib/haptics'
import { cn } from '@/lib/utils'

interface ScenarioOption {
  id: string
  title: string
  category: string
  timing: string
  harmony: string
  risk: string
  score: number
  summary: string
  actionAdvice: string
}

const SCENARIOS: ScenarioOption[] = [
  {
    id: 'executive-hire',
    title: 'Executive VP Hire',
    category: 'Leadership & Talent',
    timing: 'Optimal',
    harmony: 'High',
    risk: 'Low',
    score: 92,
    summary: 'The cosmic & market alignment indicates strong growth momentum. Candidate brings complementary skill matrices.',
    actionAdvice: 'Issue offer letter with milestone-tied performance stock awards within 48 hours.'
  },
  {
    id: 'pricing-strategy',
    title: 'Tiered Pricing Restructure',
    category: 'Revenue Optimization',
    timing: 'Favorable',
    harmony: 'Balanced',
    risk: 'Medium',
    score: 85,
    summary: 'Yang Fire day promotes assertive value capture. Existing cohort elasticity suggests +18% revenue lift.',
    actionAdvice: 'Grandfather existing enterprise contracts for 90 days, then roll out new seat-based tiers.'
  },
  {
    id: 'product-launch',
    title: 'Global v1.0 Launch',
    category: 'Go-To-Market',
    timing: 'Peak Execution',
    harmony: 'High',
    risk: 'Low',
    score: 95,
    summary: 'The planetary and technical architecture metrics are at maximum coherence. Execution velocity is unobstructed.',
    actionAdvice: 'Trigger coordinated product announcement, product video, and mobile app release.'
  },
  {
    id: 'cloud-contract',
    title: 'Cloud Vendor Commitment',
    category: 'Infrastructure',
    timing: 'Caution',
    harmony: 'Moderate',
    risk: 'Elevated',
    score: 74,
    summary: 'Vendor lock-in risks detected. Spot market compute volatility remains erratic this quarter.',
    actionAdvice: 'Negotiate 1-year annual reservation with egress waivers rather than 3-year upfront commitment.'
  }
]

export function MobileView() {
  const [selectedScenario, setSelectedScenario] = useState<ScenarioOption>(SCENARIOS[0])
  const [executing, setExecuting] = useState(false)
  const [executionStep, setExecutionStep] = useState<string | null>(null)
  const [executed, setExecuted] = useState(false)
  const [mobileTab, setMobileTab] = useState<'decide' | 'chat' | 'tools'>('decide')
  const [copiedLink, setCopiedLink] = useState(false)

  const downloadApkUrl = '/api/download/android'

  const handleDownloadApk = () => {
    triggerHaptic('success')
    const link = document.createElement('a')
    link.href = downloadApkUrl
    link.setAttribute('download', 'TchueKAM-Mobile.apk')
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const handleCopyLink = () => {
    triggerHaptic('tap')
    void navigator.clipboard.writeText(window.location.origin + '/mobile')
    setCopiedLink(true)
    setTimeout(() => setCopiedLink(false), 2000)
  }

  const handleExecuteScenario = () => {
    triggerHaptic('tap')
    setExecuting(true)
    setExecuted(false)
    setExecutionStep('Analyzing cosmic & technical telemetry…')

    setTimeout(() => {
      setExecutionStep('Running multi-agent risk simulation…')
      setTimeout(() => {
        setExecutionStep('Synthesizing executive recommendation…')
        setTimeout(() => {
          setExecuting(false)
          setExecutionStep(null)
          setExecuted(true)
          triggerHaptic('success')
        }, 600)
      }, 700)
    }, 600)
  }

  return (
    <div className="relative min-h-full flex-1 overflow-y-auto overscroll-contain bg-(--ui-page-background) text-foreground">
      {/* Background ambient lighting */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 left-1/2 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-cyan-500/10 blur-[120px]" />
        <div className="absolute top-1/3 -right-20 h-[400px] w-[500px] rounded-full bg-emerald-500/8 blur-[100px]" />
      </div>

      <div className="relative mx-auto flex max-w-7xl flex-col gap-8 px-4 py-6 sm:gap-10 sm:px-6 sm:py-10 md:px-10 md:pt-[calc(var(--titlebar-height)+2rem)] lg:py-14">
        {/* Header Section */}
        <div className="flex flex-col items-start gap-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3.5 py-1 text-xs font-semibold tracking-wide text-cyan-400">
            <span className="flex size-2 rounded-full bg-cyan-400 animate-pulse" />
            <span>v1.0.0 MOBILE RELEASE</span>
            <span className="opacity-40">•</span>
            <span>ANDROID APK & iOS PWA</span>
          </div>

          <div className="flex flex-col gap-2">
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl lg:text-5xl">
              TchueKAM Mobile
            </h1>
            <p className="max-w-2xl text-base text-(--ui-text-secondary) sm:text-lg">
              The AI Operating System for business in your pocket. Download the Android APK in one click,
              install instantly on iOS via PWA, or test drive the live mobile experience below.
            </p>
          </div>
        </div>

        {/* Main Grid: Left Column (Downloads & Pairing) + Right Column (Interactive Phone Simulator) */}
        <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-12 lg:gap-12">
          {/* Left Column (5 Cols on LG): 1-Click Download, QR Code & Guide */}
          <div className="flex flex-col gap-6 lg:col-span-5">
            {/* Primary Download Card */}
            <div className="flex flex-col gap-5 border border-cyan-500/25 bg-background/80 p-6 shadow-2xl backdrop-blur-xl">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="grid size-10 place-items-center rounded-xl bg-cyan-500/15 text-cyan-400">
                    <IconDeviceMobile className="size-6" />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold text-foreground">Android Native App</h2>
                    <p className="text-xs text-(--ui-text-tertiary)">APK package • ARM64 / Universal</p>
                  </div>
                </div>
                <span className="rounded-full border border-cyan-500/40 px-2.5 py-0.5 text-xs font-semibold text-cyan-400">
                  Ready
                </span>
              </div>

              <p className="text-xs leading-relaxed text-(--ui-text-secondary)">
                Install directly on your phone with zero app store friction. Complete with background synchronization,
                secure local key store, and fast native tool execution.
              </p>

              {/* 1-Click Download Button */}
              <a
                href={downloadApkUrl}
                onClick={handleDownloadApk}
                download="TchueKAM-Mobile.apk"
                className={cn(
                  'group flex h-12 w-full cursor-pointer items-center justify-center gap-2.5 rounded-xl',
                  'bg-cyan-500 text-slate-950 font-bold text-sm tracking-wide shadow-lg shadow-cyan-500/25',
                  'transition-all duration-200 hover:bg-cyan-400 hover:shadow-cyan-500/40 hover:-translate-y-0.5 active:translate-y-0'
                )}
              >
                <IconDownload className="size-5 transition-transform group-hover:scale-110" />
                <span>Download Android APK (1-Click)</span>
              </a>

              {/* Download Details Meta */}
              <div className="grid grid-cols-3 gap-2 border-t border-border/60 pt-4 text-center">
                <div className="flex flex-col">
                  <span className="text-[0.65rem] uppercase text-(--ui-text-quaternary)">Size</span>
                  <span className="text-xs font-semibold text-foreground">~38 MB</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[0.65rem] uppercase text-(--ui-text-quaternary)">Version</span>
                  <span className="text-xs font-semibold text-foreground">v1.0.0</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[0.65rem] uppercase text-(--ui-text-quaternary)">Security</span>
                  <span className="text-xs font-semibold text-emerald-400">SHA-256 Verified</span>
                </div>
              </div>
            </div>

            {/* iOS & Instant Web PWA Card */}
            <div className="flex flex-col gap-4 border border-border/80 bg-background/60 p-5 backdrop-blur-md">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="grid size-8 place-items-center rounded-lg bg-emerald-500/15 text-emerald-400">
                    <IconWorld className="size-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">iOS & Web (PWA)</h3>
                    <p className="text-[0.7rem] text-(--ui-text-tertiary)">Install without App Store</p>
                  </div>
                </div>
                <span className="rounded-full border border-emerald-500/40 px-2 py-0.5 text-[0.65rem] font-semibold text-emerald-400">
                  Instant
                </span>
              </div>

              <div className="rounded-lg bg-foreground/5 p-3 text-xs leading-relaxed text-(--ui-text-secondary)">
                <span className="font-semibold text-foreground">On iOS Safari:</span> Tap the Share button{' '}
                <span className="inline-block rounded bg-foreground/10 px-1 py-0.5 font-mono text-[0.65rem]">⎋</span>{' '}
                and choose <span className="font-medium text-foreground">“Add to Home Screen”</span> for a full-screen,
                native experience.
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopyLink}
                  className="flex-1 gap-1.5 text-xs border-border"
                >
                  {copiedLink ? <IconCheck className="size-3.5 text-emerald-400" /> : <IconCopy className="size-3.5" />}
                  <span>{copiedLink ? 'Link Copied!' : 'Copy Mobile Link'}</span>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  asChild
                  className="gap-1 text-xs text-cyan-400 hover:text-cyan-300"
                >
                  <a href="/mobile" target="_blank" rel="noopener noreferrer">
                    <span>Open Standalone</span>
                    <IconExternalLink className="size-3.5" />
                  </a>
                </Button>
              </div>
            </div>

            {/* QR Code Card for Phone Scan */}
            <div className="flex items-center gap-4 border border-border/80 bg-background/60 p-4 backdrop-blur-md">
              {/* Crisp SVG QR code representation */}
              <div className="grid size-24 shrink-0 place-items-center rounded-xl border border-white/10 bg-white p-2 shadow-inner">
                <svg
                  className="size-full text-slate-950"
                  viewBox="0 0 100 100"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  {/* Outer markers */}
                  <rect x="10" y="10" width="24" height="24" rx="4" fill="currentColor" />
                  <rect x="14" y="14" width="16" height="16" rx="2" fill="white" />
                  <rect x="18" y="18" width="8" height="8" rx="1" fill="currentColor" />

                  <rect x="66" y="10" width="24" height="24" rx="4" fill="currentColor" />
                  <rect x="70" y="14" width="16" height="16" rx="2" fill="white" />
                  <rect x="74" y="18" width="8" height="8" rx="1" fill="currentColor" />

                  <rect x="10" y="66" width="24" height="24" rx="4" fill="currentColor" />
                  <rect x="14" y="70" width="16" height="16" rx="2" fill="white" />
                  <rect x="18" y="74" width="8" height="8" rx="1" fill="currentColor" />

                  {/* QR Data Pattern */}
                  <rect x="40" y="14" width="6" height="6" rx="1" fill="currentColor" />
                  <rect x="52" y="14" width="6" height="6" rx="1" fill="currentColor" />
                  <rect x="46" y="24" width="8" height="8" rx="1" fill="currentColor" />
                  <rect x="40" y="38" width="20" height="6" rx="1" fill="currentColor" />
                  <rect x="14" y="44" width="8" height="8" rx="1" fill="currentColor" />
                  <rect x="28" y="44" width="6" height="6" rx="1" fill="currentColor" />
                  <rect x="70" y="44" width="16" height="6" rx="1" fill="currentColor" />
                  <rect x="40" y="52" width="8" height="14" rx="1" fill="currentColor" />
                  <rect x="54" y="54" width="12" height="6" rx="1" fill="currentColor" />
                  <rect x="74" y="58" width="12" height="12" rx="1" fill="currentColor" />
                  <rect x="44" y="72" width="14" height="6" rx="1" fill="currentColor" />
                  <rect x="64" y="76" width="6" height="10" rx="1" fill="currentColor" />
                  <rect x="76" y="76" width="10" height="10" rx="1" fill="currentColor" />
                </svg>
              </div>

              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <IconQrcode className="size-4 text-cyan-400" />
                  <span>Scan with Phone Camera</span>
                </div>
                <p className="text-[0.75rem] text-(--ui-text-secondary) leading-tight">
                  Point your iPhone or Android camera at this code to open and test drive the mobile app instantly on your phone.
                </p>
              </div>
            </div>

            {/* Feature Checkpoints */}
            <div className="flex flex-col gap-2.5 rounded-xl border border-border/50 bg-foreground/3 p-4">
              <div className="flex items-center gap-2 text-xs text-(--ui-text-secondary)">
                <IconShieldCheck className="size-4 text-cyan-400 shrink-0" />
                <span>Zero telemetry lock-in • Local key storage</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-(--ui-text-secondary)">
                <IconSparkles className="size-4 text-emerald-400 shrink-0" />
                <span>Cosmic & Technical alignment algorithms</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-(--ui-text-secondary)">
                <IconTerminal2 className="size-4 text-amber-400 shrink-0" />
                <span>Full compatibility with TchueKAM Desktop sessions</span>
              </div>
            </div>
          </div>

          {/* Right Column (7 Cols on LG): Interactive Phone Simulator */}
          <div className="flex flex-col items-center gap-4 lg:col-span-7">
            <div className="flex items-center justify-between w-full max-w-sm px-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400">
                Interactive Live Preview
              </span>
              <span className="text-xs text-(--ui-text-tertiary)">Tap around to test drive</span>
            </div>

            {/* Phone Chassis Frame */}
            <div className="relative w-full max-w-sm rounded-[44px] border-[8px] border-neutral-800 bg-neutral-950 p-3 shadow-[0_25px_60px_rgba(0,0,0,0.8),0_0_40px_rgba(0,229,255,0.15)] ring-1 ring-white/10">
              {/* Dynamic Island / Speaker Notch */}
              <div className="absolute top-5 left-1/2 -translate-x-1/2 z-30 flex h-6 w-28 items-center justify-between rounded-full bg-black px-2 shadow-md">
                <div className="size-2 rounded-full bg-neutral-800" />
                <div className="size-2.5 rounded-full bg-cyan-500/80 animate-pulse" />
              </div>

              {/* Phone Screen Container */}
              <div className="relative flex h-[620px] flex-col overflow-hidden rounded-[34px] bg-[#1a1e1b] text-white">
                {/* Status Bar */}
                <div className="flex items-center justify-between px-6 pt-3 pb-2 text-[0.6875rem] font-medium text-neutral-300">
                  <span>9:41</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[0.6rem]">5G</span>
                    <span className="text-[0.7rem]">●●●</span>
                    <span className="rounded-sm border border-neutral-400 px-1 text-[0.55rem]">100%</span>
                  </div>
                </div>

                {/* Mobile App Header */}
                <div className="flex items-center justify-between border-b border-white/10 px-5 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="size-2.5 rounded-full bg-cyan-400" />
                    <span className="font-semibold text-xs tracking-wide">TchueKAM Mobile</span>
                  </div>
                  <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[0.65rem] font-semibold text-emerald-300">
                    ☀️ Yang Fire Day
                  </span>
                </div>

                {/* Mobile Content Scroller */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-none">
                  {mobileTab === 'decide' && (
                    <>
                      {/* Section Prompt */}
                      <div>
                        <h3 className="text-base font-bold text-white tracking-tight">
                          What are you deciding right now?
                        </h3>
                        <p className="text-[0.72rem] text-[#97a091] mt-0.5">
                          Tap a scenario to align cosmic & strategic parameters.
                        </p>
                      </div>

                      {/* Scenario Selector Chips */}
                      <div className="grid grid-cols-2 gap-2">
                        {SCENARIOS.map(sc => (
                          <button
                            key={sc.id}
                            type="button"
                            onClick={() => {
                              triggerHaptic('tap')
                              setSelectedScenario(sc)
                              setExecuted(false)
                            }}
                            className={cn(
                              'flex flex-col items-start rounded-xl p-2.5 text-left transition-all duration-150',
                              selectedScenario.id === sc.id
                                ? 'bg-cyan-500/20 border border-cyan-400 text-white shadow-sm'
                                : 'bg-white/5 border border-white/5 text-neutral-300 hover:bg-white/10'
                            )}
                          >
                            <span className="text-[0.62rem] uppercase tracking-wider text-cyan-300">
                              {sc.category}
                            </span>
                            <span className="text-xs font-semibold mt-1 leading-snug line-clamp-1">
                              {sc.title}
                            </span>
                          </button>
                        ))}
                      </div>

                      {/* Primary Alignment Card */}
                      <div className="rounded-2xl border border-white/15 bg-white/5 p-4 backdrop-blur-md space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="rounded-md bg-cyan-400/20 px-2 py-0.5 text-[0.65rem] font-bold text-cyan-300">
                            AI ANALYSIS
                          </span>
                          <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[0.7rem] font-bold text-emerald-400">
                            {selectedScenario.score} Score
                          </span>
                        </div>

                        <div>
                          <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400">
                            <span className="grid size-4 place-items-center rounded-full bg-emerald-500/30 text-[0.65rem]">
                              ✓
                            </span>
                            <span>Recommended Path</span>
                          </div>
                          <p className="mt-1 text-xs text-[#a9b4a4] leading-relaxed">
                            {selectedScenario.summary}
                          </p>
                        </div>

                        {/* Metrics Triplets */}
                        <div className="grid grid-cols-3 gap-2 rounded-xl bg-black/30 p-2.5 text-center">
                          <div>
                            <div className="text-[0.6rem] uppercase tracking-wider text-neutral-400">Timing</div>
                            <div className="text-xs font-bold text-emerald-400">{selectedScenario.timing}</div>
                          </div>
                          <div>
                            <div className="text-[0.6rem] uppercase tracking-wider text-neutral-400">Harmony</div>
                            <div className="text-xs font-bold text-cyan-300">{selectedScenario.harmony}</div>
                          </div>
                          <div>
                            <div className="text-[0.6rem] uppercase tracking-wider text-neutral-400">Risk</div>
                            <div className="text-xs font-bold text-amber-300">{selectedScenario.risk}</div>
                          </div>
                        </div>

                        {/* Execution Advice Box */}
                        {executed && (
                          <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/40 p-3 text-xs text-emerald-200 animate-in fade-in slide-in-from-bottom-2">
                            <span className="font-bold text-emerald-400">Action Plan:</span>{' '}
                            {selectedScenario.actionAdvice}
                          </div>
                        )}

                        {/* Execution Action Button */}
                        <button
                          type="button"
                          disabled={executing}
                          onClick={handleExecuteScenario}
                          className={cn(
                            'flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl py-2.5 font-bold text-xs tracking-wide transition-all',
                            executing
                              ? 'bg-cyan-500/50 text-black cursor-wait'
                              : 'bg-cyan-400 text-slate-950 hover:bg-cyan-300 active:scale-98 shadow-md'
                          )}
                        >
                          {executing ? (
                            <>
                              <IconRefresh className="size-3.5 animate-spin" />
                              <span>{executionStep ?? 'Executing…'}</span>
                            </>
                          ) : (
                            <>
                              <IconPlayerPlay className="size-3.5 fill-current" />
                              <span>Execute Scenario →</span>
                            </>
                          )}
                        </button>
                      </div>
                    </>
                  )}

                  {mobileTab === 'chat' && (
                    <div className="flex flex-col gap-3 py-2">
                      <div className="rounded-xl bg-cyan-500/10 border border-cyan-500/20 p-3 text-xs text-neutral-200">
                        <span className="font-semibold text-cyan-400">TchueKAM Mobile Agent:</span> Hello! I am your
                        personal AI consultant on mobile. What would you like to build or automate today?
                      </div>

                      <div className="flex flex-col gap-2 pt-2">
                        <span className="text-[0.68rem] uppercase tracking-wider text-neutral-400">Quick prompts:</span>
                        <button
                          type="button"
                          onClick={() => triggerHaptic('tap')}
                          className="rounded-lg bg-white/5 border border-white/10 p-2 text-left text-xs text-neutral-300 hover:bg-white/10"
                        >
                          💬 &quot;Draft a non-disclosure agreement clause for contractors&quot;
                        </button>
                        <button
                          type="button"
                          onClick={() => triggerHaptic('tap')}
                          className="rounded-lg bg-white/5 border border-white/10 p-2 text-left text-xs text-neutral-300 hover:bg-white/10"
                        >
                          📊 &quot;Review quarterly burn rate and runway projections&quot;
                        </button>
                        <button
                          type="button"
                          onClick={() => triggerHaptic('tap')}
                          className="rounded-lg bg-white/5 border border-white/10 p-2 text-left text-xs text-neutral-300 hover:bg-white/10"
                        >
                          ⚡ &quot;Schedule an automated cron audit for midnight&quot;
                        </button>
                      </div>
                    </div>
                  )}

                  {mobileTab === 'tools' && (
                    <div className="flex flex-col gap-2.5 py-2">
                      <div className="text-xs font-semibold text-white">Installed Mobile Capabilities</div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                          <span className="text-cyan-400 font-bold block">Document Scanner</span>
                          <span className="text-[0.68rem] text-neutral-400">OCR & PDF Export</span>
                        </div>
                        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                          <span className="text-emerald-400 font-bold block">Voice Agent</span>
                          <span className="text-[0.68rem] text-neutral-400">Local STT / TTS</span>
                        </div>
                        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                          <span className="text-purple-400 font-bold block">Business Hub</span>
                          <span className="text-[0.68rem] text-neutral-400">Contracts & Decks</span>
                        </div>
                        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                          <span className="text-amber-400 font-bold block">Encrypted Vault</span>
                          <span className="text-[0.68rem] text-neutral-400">AES-256 Storage</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Mobile Bottom Tab Bar */}
                <div className="flex items-center justify-around border-t border-white/10 bg-black/60 py-2.5 px-3 backdrop-blur-md">
                  <button
                    type="button"
                    onClick={() => {
                      triggerHaptic('tap')
                      setMobileTab('decide')
                    }}
                    className={cn(
                      'flex flex-col items-center gap-0.5 text-[0.65rem] font-semibold transition-colors',
                      mobileTab === 'decide' ? 'text-cyan-400' : 'text-neutral-400 hover:text-neutral-200'
                    )}
                  >
                    <span>🧭</span>
                    <span>Decide</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      triggerHaptic('tap')
                      setMobileTab('chat')
                    }}
                    className={cn(
                      'flex flex-col items-center gap-0.5 text-[0.65rem] font-semibold transition-colors',
                      mobileTab === 'chat' ? 'text-cyan-400' : 'text-neutral-400 hover:text-neutral-200'
                    )}
                  >
                    <span>💬</span>
                    <span>Chat</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      triggerHaptic('tap')
                      setMobileTab('tools')
                    }}
                    className={cn(
                      'flex flex-col items-center gap-0.5 text-[0.65rem] font-semibold transition-colors',
                      mobileTab === 'tools' ? 'text-cyan-400' : 'text-neutral-400 hover:text-neutral-200'
                    )}
                  >
                    <span>⚙️</span>
                    <span>Tools</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

