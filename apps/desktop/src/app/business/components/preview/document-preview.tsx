import { useState } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { cn } from '@/lib/utils'

import { serializeBusinessDocument } from '../../exporters/document-serializer'
import { ALL_TEMPLATES, CV_TEMPLATES } from '../../schemas'
import type {
  BusinessDocument,
  CVData,
  CVTemplateId,
  InvoiceData,
  PitchDeckData
} from '../../types'
import { formatCurrency } from '../../utils/calculations'

interface DocumentPreviewProps {
  activeSlideIndex?: number
  document: BusinessDocument
  onSelectSlide?: (idx: number) => void
}

export function DocumentPreview({
  activeSlideIndex = 0,
  document: doc,
  onSelectSlide
}: DocumentPreviewProps) {
  const [zoom, setZoom] = useState<75 | 100 | 125>(100)

  const template =
    CV_TEMPLATES[doc.templateId as CVTemplateId] ??
    ALL_TEMPLATES.find(t => t.id === doc.templateId) ??
    ALL_TEMPLATES[0]

  const fontClass =
    template?.fontFamily === 'serif'
      ? 'font-serif'
      : template?.fontFamily === 'mono'
        ? 'font-mono'
        : 'font-sans'

  const accentColor = template?.accentColor ?? '#0053FD'

  if (doc.type === 'deck') {
    const deck = doc.data as PitchDeckData
    const slides = deck.slides
    const safeIdx = Math.min(Math.max(0, activeSlideIndex), Math.max(0, slides.length - 1))
    const currentSlide = slides[safeIdx]

    return (
      <div className="flex h-full flex-col bg-slate-100/70 dark:bg-zinc-950/40">
        {/* Apple Keynote Style Presentation Bar */}
        <div className="flex items-center justify-between border-b border-border/70 bg-card/80 px-4 py-2.5 text-xs backdrop-blur-md">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-lg bg-primary/10 px-2 py-0.5 text-[0.6875rem] font-semibold text-primary">
              <Codicon name="preview" size="0.8rem" />
              <span>Slide {safeIdx + 1} of {slides.length}</span>
            </div>
            <span className="hidden text-[0.6875rem] text-muted-foreground sm:inline">
              16:9 Keynote / Investor Deck
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              aria-label="Previous slide"
              className="inline-flex h-7 items-center gap-1 rounded-lg border border-border/70 bg-background/80 px-2.5 text-xs font-semibold shadow-2xs transition hover:bg-muted disabled:opacity-40"
              disabled={safeIdx <= 0}
              onClick={() => onSelectSlide?.(safeIdx - 1)}
              type="button"
            >
              <Codicon name="arrow-left" size="0.75rem" />
              Prev
            </button>
            <button
              aria-label="Next slide"
              className="inline-flex h-7 items-center gap-1 rounded-lg border border-border/70 bg-background/80 px-2.5 text-xs font-semibold shadow-2xs transition hover:bg-muted disabled:opacity-40"
              disabled={safeIdx >= slides.length - 1}
              onClick={() => onSelectSlide?.(safeIdx + 1)}
              type="button"
            >
              Next
              <Codicon name="arrow-right" size="0.75rem" />
            </button>
          </div>
        </div>

        <div className="flex flex-1 flex-col items-center justify-center overflow-auto p-6">
          {currentSlide && (
            <div
              className="flex aspect-video w-full max-w-2xl flex-col justify-between rounded-2xl border border-slate-200/90 dark:border-white/10 bg-white p-8 text-slate-900 shadow-[0_12px_36px_-6px_rgba(0,0,0,0.18)] dark:shadow-[0_12px_36px_rgba(0,0,0,0.6)] transition-all"
              style={{ borderTop: `6px solid ${accentColor}` }}
            >
              <div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-[0.6875rem] font-bold uppercase tracking-wider text-slate-400">
                    {deck.companyName}
                  </span>
                  {currentSlide.metricLabel && currentSlide.metricValue && (
                    <span
                      className="rounded-full px-3 py-1 text-xs font-bold text-white shadow-xs"
                      style={{ backgroundColor: accentColor }}
                    >
                      {currentSlide.metricLabel}: {currentSlide.metricValue}
                    </span>
                  )}
                </div>
                <h2 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">
                  {currentSlide.title}
                </h2>
                <p className="mt-1 text-sm font-medium text-slate-500">{currentSlide.subtitle}</p>

                <ul className="mt-6 space-y-3">
                  {currentSlide.bullets.map((bullet, i) => (
                    <li className="flex items-start gap-3 text-sm text-slate-700 leading-relaxed" key={i}>
                      <span
                        className="mt-1.5 size-2 shrink-0 rounded-full"
                        style={{ backgroundColor: accentColor }}
                      />
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="flex items-center justify-between border-t border-slate-100 pt-3 text-[0.6875rem] text-slate-400">
                <span>
                  {deck.tagline} · Target Raise:{' '}
                  {formatCurrency(deck.raiseAmount, deck.currency, doc.language)}
                </span>
                <span className="font-semibold">
                  {safeIdx + 1} / {slides.length}
                </span>
              </div>
            </div>
          )}

          {currentSlide?.speakerNotes && (
            <div className="mt-5 w-full max-w-2xl rounded-2xl border border-border/80 bg-card/90 p-4 text-xs text-muted-foreground shadow-sm backdrop-blur-sm">
              <div className="flex items-center gap-1.5 font-semibold text-foreground mb-1">
                <Codicon name="comment" size="0.8rem" />
                <span>Presenter Notes:</span>
              </div>
              <p className="leading-relaxed">{currentSlide.speakerNotes}</p>
            </div>
          )}
        </div>
      </div>
    )
  }

  const blocks = serializeBusinessDocument(doc)

  const logoUrl =
    doc.type === 'invoice' || doc.type === 'quote'
      ? (doc.data as InvoiceData).seller?.logoDataUrl
      : ''

  const isSidebarTemplate = doc.type === 'cv' && template?.headerStyle === 'sidebar'
  const cvData = doc.type === 'cv' ? (doc.data as CVData) : null

  return (
    <div className="flex h-full flex-col bg-slate-100/70 dark:bg-zinc-950/40">
      {/* Apple-style Live Sheet Toolbar */}
      <div className="flex items-center justify-between border-b border-border/70 bg-card/80 px-4 py-2.5 text-xs backdrop-blur-md">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-lg bg-primary/10 px-2 py-0.5 text-[0.6875rem] font-semibold text-primary">
            <Codicon name="file-pdf" size="0.85rem" />
            <span>A4 Document Preview</span>
          </div>
          <span className="rounded-md border border-border/60 bg-background/60 px-2 py-0.5 text-[0.6875rem] font-medium text-muted-foreground">
            {template?.name ?? doc.templateId}
          </span>
        </div>

        {/* Apple Segmented Zoom Control */}
        <div className="inline-flex rounded-lg bg-muted/60 p-0.5 border border-border/40">
          {([75, 100, 125] as const).map(level => (
            <button
              className={cn(
                'rounded-md px-2 py-0.5 text-[0.6875rem] font-semibold transition-all duration-150',
                zoom === level
                  ? 'bg-card text-foreground shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              key={level}
              onClick={() => setZoom(level)}
              type="button"
            >
              {level}%
            </button>
          ))}
        </div>
      </div>

      {/* Sheet Canvas */}
      <div className="flex-1 overflow-auto p-6 flex flex-col items-center">
        <div
          className={cn(
            'w-full max-w-[650px] min-h-[842px] rounded-xl border border-slate-200/90 dark:border-white/10 bg-white text-slate-900 shadow-[0_12px_36px_-6px_rgba(0,0,0,0.18)] dark:shadow-[0_12px_36px_rgba(0,0,0,0.6)] transition-all origin-top',
            fontClass
          )}
          data-testid="live-document-preview"
          style={{
            transform: zoom === 100 ? undefined : `scale(${zoom / 100})`,
            transformOrigin: 'top center'
          }}
        >
          {isSidebarTemplate && cvData ? (
            <div className="grid min-h-[842px] grid-cols-12">
              <div
                className="col-span-4 space-y-4 p-6 text-white"
                style={{ backgroundColor: accentColor }}
              >
                <div>
                  <h1 className="text-lg font-bold leading-snug">{cvData.fullName}</h1>
                  <p className="mt-1 text-xs opacity-90">{cvData.headline}</p>
                </div>
                <div className="space-y-1 text-[0.6875rem] opacity-90">
                  <div>{cvData.location}</div>
                  <div>{cvData.email}</div>
                  <div>{cvData.phone}</div>
                </div>
                {cvData.skills.length > 0 && (
                  <div>
                    <div className="mb-1.5 border-b border-white/25 pb-1 text-[0.6875rem] font-bold uppercase">
                      Skills
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {cvData.skills.map((skill, idx) => (
                        <span
                          className="rounded-sm bg-white/15 px-1.5 py-0.5 text-[0.65rem]"
                          key={idx}
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="col-span-8 space-y-4 p-6">
                {blocks.slice(1).map((block, idx) => (
                  <PreviewBlock accentColor={accentColor} block={block} key={idx} />
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4 p-8">
              {blocks.map((block, idx) => (
                <PreviewBlock
                  accentColor={accentColor}
                  block={block}
                  headerStyle={template?.headerStyle}
                  key={idx}
                  logoUrl={idx === 0 ? logoUrl : undefined}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function PreviewBlock({
  accentColor,
  block,
  headerStyle = 'banner',
  logoUrl
}: {
  accentColor: string
  block: ReturnType<typeof serializeBusinessDocument>[number]
  headerStyle?: 'banner' | 'centered' | 'minimal' | 'sidebar'
  logoUrl?: string
}) {
  if (block.type === 'header') {
    if (headerStyle === 'centered') {
      return (
        <div
          className="border-b-2 pb-4 text-center"
          style={{ borderColor: accentColor }}
        >
          {logoUrl && (
            <img
              alt="Company logo"
              className="mx-auto mb-2 max-h-12 object-contain"
              src={logoUrl}
            />
          )}
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: accentColor }}>
            {block.title}
          </h1>
          <p className="mt-1 text-xs text-slate-600">{block.subtitle}</p>
        </div>
      )
    }

    if (headerStyle === 'minimal') {
      return (
        <div className="border-l-4 pl-4" style={{ borderColor: accentColor }}>
          {logoUrl && (
            <img alt="Company logo" className="mb-2 max-h-10 object-contain" src={logoUrl} />
          )}
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{block.title}</h1>
          <p className="mt-1 text-xs text-slate-600">{block.subtitle}</p>
        </div>
      )
    }

    return (
      <div
        className="flex items-center justify-between gap-4 rounded-xl p-5 text-white shadow-sm"
        style={{ backgroundColor: accentColor }}
      >
        <div>
          <h1 className="text-xl font-bold tracking-tight">{block.title}</h1>
          <p className="mt-1 text-xs text-white/90">{block.subtitle}</p>
        </div>
        {logoUrl && (
          <img
            alt="Company logo"
            className="max-h-12 rounded-md bg-white p-1 object-contain shadow-xs"
            src={logoUrl}
          />
        )}
      </div>
    )
  }

  if (block.type === 'heading') {
    if (block.level === 1) {
      return (
        <h2
          className="mt-4 border-b border-slate-200 pb-1 text-xs font-bold uppercase tracking-wider"
          style={{ color: accentColor }}
        >
          {block.text}
        </h2>
      )
    }

    return <h3 className="mt-2 text-xs font-semibold text-slate-800">{block.text}</h3>
  }

  if (block.type === 'paragraph') {
    return <p className="whitespace-pre-line text-xs leading-relaxed text-slate-700">{block.text}</p>
  }

  if (block.type === 'bullets') {
    return (
      <ul className="list-disc space-y-1 pl-5 text-xs text-slate-700">
        {block.items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    )
  }

  if (block.type === 'keyValueGrid') {
    return (
      <div className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs sm:grid-cols-2">
        {block.pairs.map((pair, i) => (
          <div key={i}>
            <span className="block text-[0.65rem] font-bold uppercase text-slate-400">
              {pair.label}
            </span>
            <span className="font-medium text-slate-800">{pair.value}</span>
          </div>
        ))}
      </div>
    )
  }

  if (block.type === 'callout') {
    return (
      <div
        className={cn(
          'rounded-xl border px-3.5 py-2.5 text-xs font-medium',
          block.kind === 'warning'
            ? 'border-amber-300 bg-amber-50 text-amber-900'
            : 'border-blue-200 bg-blue-50 text-blue-900'
        )}
      >
        {block.text}
      </div>
    )
  }

  if (block.type === 'table') {
    return (
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="bg-slate-100 text-slate-700">
              {block.headers.map((h, i) => (
                <th className="border-b border-slate-200 px-3 py-2 font-semibold" key={i}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rIdx) => (
              <tr className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/50" key={rIdx}>
                {row.map((cell, cIdx) => (
                  <td className="px-3 py-2 text-slate-700" key={cIdx}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (block.type === 'signatures') {
    return (
      <div className="mt-6 grid grid-cols-2 gap-6 border-t border-slate-200 pt-4 text-xs">
        <div>
          <div className="font-semibold text-slate-800">{block.leftLabel}</div>
          <div className="mt-6 text-slate-600">{block.leftName}</div>
        </div>
        {block.rightLabel && (
          <div>
            <div className="font-semibold text-slate-800">{block.rightLabel}</div>
            <div className="mt-6 text-slate-600">{block.rightName}</div>
          </div>
        )}
      </div>
    )
  }

  return null
}
