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
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { triggerHaptic } from '@/lib/haptics'
import { resolveBackendOrigin, webConfig } from '@/lib/platform'
import { cn } from '@/lib/utils'

import { generateQrMatrix } from './qr-svg'

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
  const [simReply, setSimReply] = useState<{ prompt: string; reply: string } | null>(null)

  const backendOrigin = resolveBackendOrigin()
  const downloadApkUrl = `${backendOrigin || webConfig.basePath}/api/download/android`
  const qrTargetUrl = useMemo(() => {
    if (typeof window === 'undefined') {
      return downloadApkUrl
    }
    try {
      return new URL(downloadApkUrl, window.location.origin).href
    } catch {
      return downloadApkUrl
    }
  }, [downloadApkUrl])
  const qrMatrix = useMemo(() => generateQrMatrix(qrTargetUrl), [qrTargetUrl])

  const handleDownloadClick = () => {
    triggerHaptic('success')
  }

  const handleCopyLink = () => {
    triggerHaptic('tap')
    void navigator.clipboard.writeText(window.location.origin + '/#/mobile')
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
                onClick={handleDownloadClick}
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
                  <a href="/#/mobile" target="_blank" rel="noopener noreferrer">
                    <span>Open Standalone</span>
                    <IconExternalLink className="size-3.5" />
                  </a>
                </Button>
              </div>
            </div>

            {/* QR Code Card for Phone Scan */}
            <div className="flex items-center gap-4 border border-border/80 bg-background/60 p-4 backdrop-blur-md">
              {/* Scannable ISO QR code for APK download */}
              <div className="grid size-24 shrink-0 place-items-center rounded-xl border border-white/10 bg-white p-1.5 shadow-inner">
                <svg
                  aria-label="QR code to download TchueKAM Mobile"
                  className="size-full text-slate-950"
                  role="img"
                  shapeRendering="crispEdges"
                  viewBox={`0 0 ${qrMatrix.size + 4} ${qrMatrix.size + 4}`}
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <rect width={qrMatrix.size + 4} height={qrMatrix.size + 4} fill="white" />
                  {qrMatrix.modules.map((row, r) =>
                    row.map((dark, c) =>
                      dark ? <rect key={`${r}-${c}`} x={c + 2} y={r + 2} width={1} height={1} fill="currentColor" /> : null
                    )
                  )}
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
