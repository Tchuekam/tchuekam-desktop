import type * as React from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ZoomableImage } from '@/components/chat/zoomable-image'
import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { Textarea } from '@/components/ui/textarea'
import { getSessionMessages, listSessions } from '@/hermes'
import { cn } from '@/lib/utils'
import { notifyError } from '@/store/notifications'
import type { SessionInfo, SessionMessage } from '@/types/hermes'

import { collectArtifactsForSession } from '../artifacts'
import { PageSearchShell } from '../page-search-shell'
import { NEW_CHAT_ROUTE } from '../routes'
import type { SetStatusbarItemGroup } from '../shell/statusbar-controls'

interface GeneratedImage {
  id: string
  href: string
  label: string
  sessionId: string
  sessionTitle: string
  timestamp: number
}

const ASPECT_RATIOS = [
  { label: '1:1', value: '1:1', width: 1024, height: 1024 },
  { label: '16:9', value: '16:9', width: 1792, height: 1024 },
  { label: '9:16', value: '9:16', width: 1024, height: 1792 },
  { label: '4:3', value: '4:3', width: 1024, height: 768 },
  { label: '3:2', value: '3:2', width: 1536, height: 1024 }
] as const

type AspectRatio = (typeof ASPECT_RATIOS)[number]['value']

const STYLE_PRESETS = [
  { label: 'Photorealistic', prompt: 'photorealistic, high detail, 8k resolution, professional photography' },
  { label: 'Digital Art', prompt: 'digital art, concept art, trending on artstation, vibrant colors' },
  { label: 'Watercolor', prompt: 'watercolor painting, soft edges, artistic, traditional media' },
  { label: 'Sketch', prompt: 'pencil sketch, detailed line art, hand drawn' },
  { label: 'Cinematic', prompt: 'cinematic, dramatic lighting, movie still, anamorphic lens' },
  { label: 'Minimal', prompt: 'minimalist, clean design, simple, flat illustration' }
]

interface ImageStudioViewProps extends React.ComponentProps<'section'> {
  setStatusbarItemGroup?: SetStatusbarItemGroup
}

export function ImageStudioView({ setStatusbarItemGroup: _unused, ...props }: ImageStudioViewProps) {
  const navigate = useNavigate()
  const [prompt, setPrompt] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>('1:1')
  const [stylePreset, setStylePreset] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [images, setImages] = useState<GeneratedImage[] | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState('')
  const [failedIds, setFailedIds] = useState<Set<string>>(() => new Set())
  const promptRef = useRef<HTMLTextAreaElement>(null)

  const refreshImages = useCallback(async () => {
    setRefreshing(true)
    try {
      const sessions = (await listSessions(20, 1)).sessions
      const results = await Promise.allSettled(sessions.map(s => getSessionMessages(s.id)))
      const next: GeneratedImage[] = []

      results.forEach((result, index) => {
        if (result.status !== 'fulfilled') return
        const session = sessions[index]
        const artifacts = collectArtifactsForSession(session, result.value.messages)
        for (const a of artifacts) {
          if (a.kind === 'image') {
            next.push({
              id: a.id,
              href: a.href,
              label: a.label,
              sessionId: a.sessionId,
              sessionTitle: a.sessionTitle,
              timestamp: a.timestamp
            })
          }
        }
      })

      setImages(next.sort((a, b) => b.timestamp - a.timestamp))
    } catch (err) {
      notifyError(err, 'Failed to load image gallery')
      setImages([])
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void refreshImages()
  }, [refreshImages])

  const visibleImages = useMemo(() => {
    if (!images) return []
    const q = query.trim().toLowerCase()
    if (!q) return images
    return images.filter(img => img.label.toLowerCase().includes(q) || img.sessionTitle.toLowerCase().includes(q))
  }, [images, query])

  function buildFullPrompt(): string {
    const parts = [prompt.trim()]
    if (stylePreset) parts.push(stylePreset)
    if (negativePrompt.trim()) parts.push(`Negative: ${negativePrompt.trim()}`)
    const ratio = ASPECT_RATIOS.find(r => r.value === aspectRatio)
    if (ratio) parts.push(`Aspect ratio: ${ratio.value} (${ratio.width}x${ratio.height}px)`)
    return parts.join('. ')
  }

  function handleGenerate() {
    const fullPrompt = buildFullPrompt()
    if (!fullPrompt.trim()) return

    // Pre-fill the new session with an image generation request
    try {
      window.sessionStorage.setItem('tchuekam.pending-prompt', `Generate an image: ${fullPrompt}`)
    } catch {
      // Best-effort
    }
    navigate(NEW_CHAT_ROUTE)
  }

  const markFailed = useCallback((id: string) => {
    setFailedIds(prev => (prev.has(id) ? prev : new Set(prev).add(id)))
  }, [])

  const openImage = useCallback(async (href: string) => {
    try {
      if (window.hermesDesktop?.openExternal) {
        await window.hermesDesktop.openExternal(href)
      } else {
        window.open(href, '_blank', 'noopener,noreferrer')
      }
    } catch {
      // Best-effort
    }
  }, [])

  return (
    <PageSearchShell
      {...props}
      onSearchChange={setQuery}
      searchPlaceholder="Search generated images…"
      searchTrailingAction={
        <Button
          aria-label={refreshing ? 'Refreshing gallery' : 'Refresh gallery'}
          className="text-(--ui-text-tertiary) hover:bg-transparent hover:text-foreground"
          disabled={refreshing}
          onClick={() => void refreshImages()}
          size="icon-xs"
          title="Refresh gallery"
          type="button"
          variant="ghost"
        >
          <Codicon name="refresh" size="0.875rem" spinning={refreshing} />
        </Button>
      }
      searchValue={query}
    >
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        {/* Prompt workspace */}
        <div className="shrink-0 space-y-3 border-b border-(--ui-stroke-tertiary) p-4">
          {/* Main prompt */}
          <div className="relative">
            <Textarea
              className="min-h-20 resize-none pr-24 text-sm"
              onChange={e => setPrompt(e.target.value)}
              onKeyDown={e => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                  e.preventDefault()
                  handleGenerate()
                }
              }}
              placeholder="Describe the image you want to generate…"
              ref={promptRef}
              value={prompt}
            />
            <Button
              className="absolute bottom-2 right-2 gap-1.5"
              disabled={!prompt.trim()}
              onClick={handleGenerate}
              size="sm"
              type="button"
            >
              <Codicon name="sparkle" size="0.75rem" />
              Generate
            </Button>
          </div>

          {/* Style presets */}
          <div className="flex flex-wrap gap-1.5">
            {STYLE_PRESETS.map(preset => (
              <button
                className={cn(
                  'rounded-full border px-2.5 py-0.5 text-xs transition-colors',
                  stylePreset === preset.prompt
                    ? 'border-blue-500/60 bg-blue-500/10 text-blue-600 dark:text-blue-400'
                    : 'border-(--ui-stroke-tertiary) text-(--ui-text-secondary) hover:border-(--ui-stroke-secondary) hover:text-foreground'
                )}
                key={preset.label}
                onClick={() => setStylePreset(prev => (prev === preset.prompt ? null : preset.prompt))}
                type="button"
              >
                {preset.label}
              </button>
            ))}
          </div>

          {/* Aspect ratio */}
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-xs text-muted-foreground">Ratio</span>
            <div className="flex gap-1.5">
              {ASPECT_RATIOS.map(ratio => (
                <button
                  className={cn(
                    'rounded-md border px-2 py-0.5 text-xs transition-colors',
                    aspectRatio === ratio.value
                      ? 'border-blue-500/60 bg-blue-500/10 text-blue-600 dark:text-blue-400'
                      : 'border-(--ui-stroke-tertiary) text-(--ui-text-secondary) hover:bg-(--ui-control-hover-background) hover:text-foreground'
                  )}
                  key={ratio.value}
                  onClick={() => setAspectRatio(ratio.value)}
                  type="button"
                >
                  {ratio.label}
                </button>
              ))}
            </div>

            <button
              className="ml-auto flex items-center gap-1 text-xs text-(--ui-text-tertiary) hover:text-foreground"
              onClick={() => setShowAdvanced(v => !v)}
              type="button"
            >
              <Codicon name={showAdvanced ? 'chevron-up' : 'chevron-down'} size="0.75rem" />
              Advanced
            </button>
          </div>

          {/* Advanced controls */}
          {showAdvanced && (
            <div className="space-y-2 rounded-lg border border-(--ui-stroke-tertiary) p-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Negative prompt</label>
                <Textarea
                  className="min-h-12 resize-none text-xs"
                  onChange={e => setNegativePrompt(e.target.value)}
                  placeholder="Elements to avoid: blurry, distorted, ugly…"
                  value={negativePrompt}
                />
              </div>
            </div>
          )}
        </div>

        {/* Gallery */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {!images ? (
            <PageLoader label="Loading image gallery…" />
          ) : visibleImages.length === 0 ? (
            <GalleryEmpty hasQuery={query.trim().length > 0} onGenerate={() => promptRef.current?.focus()} />
          ) : (
            <div className="p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{visibleImages.length} image{visibleImages.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-2">
                {visibleImages.map(img => (
                  <ImageCard
                    failed={failedIds.has(img.id)}
                    image={img}
                    key={img.id}
                    onFailure={markFailed}
                    onOpen={() => void openImage(img.href)}
                    onOpenChat={() => navigate(`/${img.sessionId}`)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </PageSearchShell>
  )
}

// ─── Gallery components ────────────────────────────────────────────────────────

interface ImageCardProps {
  image: GeneratedImage
  failed: boolean
  onOpen: () => void
  onOpenChat: () => void
  onFailure: (id: string) => void
}

function ImageCard({ image, failed, onOpen, onOpenChat, onFailure }: ImageCardProps) {
  return (
    <article className="group/img overflow-hidden rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-chat-bubble-background) shadow-sm transition-shadow hover:shadow-md">
      <div
        className={cn(
          'relative flex h-36 items-center justify-center overflow-hidden bg-(--ui-bg-quinary)',
          !failed && 'cursor-zoom-in'
        )}
        onClick={!failed ? onOpen : undefined}
      >
        {failed ? (
          <div className="grid place-items-center gap-1 text-(--ui-text-tertiary)">
            <Codicon name="image" size="1.5rem" />
            <span className="text-[0.6rem]">Unavailable</span>
          </div>
        ) : (
          <ZoomableImage
            alt={image.label}
            className="max-h-36 max-w-full object-contain"
            decoding="async"
            loading="lazy"
            onError={() => onFailure(image.id)}
            src={image.href}
          />
        )}
        <div className="absolute inset-0 flex items-end justify-end gap-1 bg-gradient-to-t from-black/30 to-transparent p-1.5 opacity-0 transition-opacity group-hover/img:opacity-100">
          <button
            className="grid size-6 place-items-center rounded-md bg-black/50 text-white backdrop-blur-sm hover:bg-black/70"
            onClick={e => { e.stopPropagation(); onOpenChat() }}
            title="Open in chat"
            type="button"
          >
            <Codicon name="comment" size="0.75rem" />
          </button>
        </div>
      </div>
      <div className="px-2 py-1.5">
        <div className="truncate text-[0.625rem] text-(--ui-text-tertiary)">{image.sessionTitle}</div>
      </div>
    </article>
  )
}

function GalleryEmpty({ hasQuery, onGenerate }: { hasQuery: boolean; onGenerate: () => void }) {
  return (
    <div className="grid min-h-52 place-items-center text-center">
      <div className="space-y-3">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-(--ui-bg-quinary) text-2xl">🎨</div>
        <div>
          <div className="text-sm font-medium">{hasQuery ? 'No images match' : 'No images yet'}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {hasQuery ? 'Try a broader search.' : 'Images generated in your sessions will appear here.'}
          </div>
        </div>
        {!hasQuery && (
          <Button className="gap-1.5 text-xs" onClick={onGenerate} size="sm" type="button" variant="outline">
            <Codicon name="sparkle" size="0.75rem" />
            Generate your first image
          </Button>
        )}
      </div>
    </div>
  )
}
