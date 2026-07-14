import { useState } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { cn } from '@/lib/utils'

/**
 * Marketing Studio (renamed from Image Studio) — a cinematic, always-dark
 * creative space: image generation, image understanding and text-from-image.
 * Committed single-world dark theme. UI/UX only; backend lands later (Fable 5).
 */

type Tab = 'gen' | 'und' | 'txt'

const PALETTES: Record<string, string> = {
  ankara:
    'radial-gradient(60% 65% at 28% 26%,#E5484D,transparent 60%),radial-gradient(70% 70% at 82% 82%,#C98A2B,transparent 60%),radial-gradient(50% 50% at 60% 40%,#7a1f2b,transparent 70%),#2a0d10',
  studio:
    'radial-gradient(60% 65% at 30% 24%,#3D7BFF,transparent 60%),radial-gradient(70% 70% at 80% 80%,#8B46FF,transparent 60%),#0a1030',
  street:
    'radial-gradient(60% 60% at 25% 30%,#1F8A65,transparent 60%),radial-gradient(70% 70% at 82% 78%,#C98A2B,transparent 60%),#08201f',
  afro:
    'radial-gradient(55% 60% at 28% 26%,#8B46FF,transparent 60%),radial-gradient(60% 60% at 80% 80%,#FF5D73,transparent 60%),radial-gradient(45% 45% at 60% 45%,#2ad0ff,transparent 70%),#160b2b',
  toghu:
    'radial-gradient(55% 60% at 26% 26%,#0053FD,transparent 60%),radial-gradient(55% 55% at 82% 80%,#E5484D,transparent 60%),radial-gradient(45% 45% at 55% 55%,#E5B45C,transparent 70%),#0a1440',
  food:
    'radial-gradient(60% 65% at 30% 26%,#E5B45C,transparent 60%),radial-gradient(65% 65% at 80% 80%,#E5484D,transparent 60%),#2a1408'
}

interface Preset {
  label: string
  pal: keyof typeof PALETTES
  swatch: string
}

const PRESETS: Preset[] = [
  { label: 'Ankara Editorial', pal: 'ankara', swatch: 'linear-gradient(135deg,#E5484D,#C98A2B)' },
  { label: 'Studio Produit', pal: 'studio', swatch: 'linear-gradient(135deg,#3D7BFF,#8B46FF)' },
  { label: 'Street Douala', pal: 'street', swatch: 'linear-gradient(135deg,#1F8A65,#C98A2B)' },
  { label: 'Afrofuture', pal: 'afro', swatch: 'linear-gradient(135deg,#8B46FF,#FF5D73)' },
  { label: 'Toghu Luxe', pal: 'toghu', swatch: 'linear-gradient(135deg,#0053FD,#E5484D)' },
  { label: 'Menu Food', pal: 'food', swatch: 'linear-gradient(135deg,#C98A2B,#E5B45C)' }
]

const RATIOS = ['1:1', '4:5', '9:16', '16:9']

interface Shot {
  id: number
  pal: keyof typeof PALETTES
  caption: string
  h: number
}

const INITIAL_SHOTS: Shot[] = [
  { id: 1, pal: 'ankara', caption: 'Ankara editorial · Douala', h: 220 },
  { id: 2, pal: 'studio', caption: 'Studio produit · parfum', h: 280 },
  { id: 3, pal: 'afro', caption: 'Afrofuture portrait', h: 340 },
  { id: 4, pal: 'toghu', caption: 'Toghu luxe · portrait', h: 220 },
  { id: 5, pal: 'food', caption: 'Menu food · poulet DG', h: 280 },
  { id: 6, pal: 'street', caption: 'Street style · Bonapriso', h: 340 },
  { id: 7, pal: 'studio', caption: 'Packshot cosmétique', h: 220 },
  { id: 8, pal: 'ankara', caption: 'Robe wax · lookbook', h: 280 },
  { id: 9, pal: 'afro', caption: 'Néon Yaoundé nuit', h: 300 }
]

const CARD = 'rounded-2xl border border-white/8 bg-[#12131C]'

function StudioTile({ shot }: { shot: Shot }) {
  return (
    <div className="group relative mb-3 break-inside-avoid overflow-hidden rounded-xl border border-white/8 shadow-[0_20px_40px_-24px_#000]">
      <div style={{ height: shot.h, background: PALETTES[shot.pal] }} />
      <div className="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/70 to-transparent px-3 pb-2.5 pt-7 text-[0.6875rem] font-semibold opacity-0 transition group-hover:opacity-100">
        <Codicon name="sparkle" size="0.8rem" />
        <span className="truncate">{shot.caption}</span>
        <span className="ml-auto rounded bg-white/15 px-1.5 py-0.5 text-[0.5625rem]">HD</span>
      </div>
    </div>
  )
}

export function MarketingView() {
  const [tab, setTab] = useState<Tab>('gen')
  const [preset, setPreset] = useState(0)
  const [ratio, setRatio] = useState(0)
  const [prompt, setPrompt] = useState('')
  const [shots, setShots] = useState<Shot[]>(INITIAL_SHOTS)

  const generate = () => {
    const p = PRESETS[preset]
    const cap = prompt.trim() ? (prompt.length > 32 ? `${prompt.slice(0, 32)}…` : prompt) : p.label
    const heights = [220, 300, 260]
    const next: Shot[] = heights.map((h, i) => ({ id: Date.now() + i, pal: p.pal, caption: cap, h }))
    setShots(prev => [...next, ...prev])
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto overflow-x-hidden bg-[#08090E] pt-(--titlebar-height) text-[#F3F4FA]">
      {/* Hero */}
      <div
        className="relative overflow-hidden border-b border-white/8 px-8 pb-6 pt-7"
        style={{
          background:
            'radial-gradient(40% 120% at 15% 0%,rgba(139,70,255,.35),transparent 60%),radial-gradient(40% 120% at 85% 10%,rgba(255,93,115,.3),transparent 60%),radial-gradient(50% 140% at 55% 0%,rgba(61,123,255,.3),transparent 55%)'
        }}
      >
        <div className="mx-auto max-w-5xl">
          <div className="text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-white/60">Creative studio</div>
          <h1 className="mt-2.5 text-3xl font-semibold tracking-tight">
            Marketing{' '}
            <span
              className="bg-clip-text text-transparent"
              style={{ backgroundImage: 'linear-gradient(100deg,#3D7BFF,#8B46FF 45%,#FF5D73)' }}
            >
              Studio
            </span>
          </h1>
          <p className="mt-2 max-w-xl text-sm text-white/65">
            Generate brand visuals, understand your images and pull text from any picture — to sell in Cameroon and the
            world.
          </p>
          <div className="mt-5 inline-flex gap-1 rounded-xl border border-white/8 bg-[#12131C] p-1">
            {(
              [
                ['gen', 'wand', 'Generate'],
                ['und', 'eye', 'Understand'],
                ['txt', 'text-size', 'Text from image']
              ] as const
            ).map(([id, icon, label]) => (
              <button
                className={cn(
                  'inline-flex h-9 items-center gap-2 rounded-lg px-4 text-[0.8125rem] font-semibold transition',
                  tab === id ? 'bg-[#171826] text-white shadow-sm' : 'text-white/60 hover:text-white'
                )}
                key={id}
                onClick={() => setTab(id)}
                type="button"
              >
                <Codicon name={icon} size="0.9rem" />
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto w-full max-w-5xl px-8 pb-24 pt-6">
        {/* GENERATE */}
        {tab === 'gen' && (
          <>
            <div className="rounded-2xl border border-white/8 bg-gradient-to-b from-[#171826] to-[#12131C] p-4 shadow-[0_30px_60px_-30px_#000]">
              <textarea
                className="min-h-[56px] w-full resize-none bg-transparent p-1 text-base leading-relaxed placeholder:text-white/35 focus:outline-none"
                onChange={e => setPrompt(e.target.value)}
                placeholder="Describe your visual: “Model in an Ankara dress in front of a Douala building, golden evening light, editorial style”"
                rows={1}
                value={prompt}
              />
              <div className="flex flex-wrap gap-2 px-1 pt-1.5">
                {PRESETS.map((p, i) => (
                  <button
                    className={cn(
                      'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition',
                      preset === i
                        ? 'border-[#8B46FF] bg-[#8B46FF]/16 text-white'
                        : 'border-white/8 bg-white/[0.04] text-white/60 hover:text-white'
                    )}
                    key={p.label}
                    onClick={() => setPreset(i)}
                    type="button"
                  >
                    <span className="size-3 rounded" style={{ background: p.swatch }} />
                    {p.label}
                  </button>
                ))}
              </div>
              <div className="mt-3.5 flex flex-wrap items-center gap-2.5 border-t border-white/8 pt-3.5">
                <span className="inline-flex h-9 items-center gap-2 rounded-lg border border-white/8 bg-white/[0.04] px-3 text-xs font-semibold text-white/70">
                  <Codicon name="settings" size="0.85rem" />
                  Cinematic v3
                </span>
                <div className="flex gap-1.5">
                  {RATIOS.map((r, i) => (
                    <button
                      className={cn(
                        'grid h-8 min-w-9 place-items-center rounded-lg border px-2 text-[0.6875rem] font-bold transition',
                        ratio === i
                          ? 'border-[#3D7BFF] bg-[#3D7BFF]/18 text-white'
                          : 'border-white/8 bg-white/[0.04] text-white/45'
                      )}
                      key={r}
                      onClick={() => setRatio(i)}
                      type="button"
                    >
                      {r}
                    </button>
                  ))}
                </div>
                <button
                  className="ml-auto inline-flex h-10 items-center gap-2 rounded-xl px-5 text-sm font-bold text-white shadow-lg transition hover:brightness-110"
                  onClick={generate}
                  style={{ background: 'linear-gradient(100deg,#3D7BFF,#8B46FF 55%,#FF5D73)' }}
                  type="button"
                >
                  <Codicon name="sparkle" size="1rem" />
                  Generate
                </button>
              </div>
            </div>

            <div className="mb-3.5 mt-7 flex items-center">
              <h3 className="text-base font-semibold">Your creations</h3>
              <span className="ml-auto text-xs text-white/40">{shots.length} visuals</span>
            </div>
            <div className="[column-gap:0.75rem] [columns:2] sm:[columns:3] lg:[columns:4]">
              {shots.map(s => (
                <StudioTile key={s.id} shot={s} />
              ))}
            </div>
          </>
        )}

        {/* UNDERSTAND */}
        {tab === 'und' && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className={cn(CARD, 'relative min-h-[320px] overflow-hidden p-0')}>
              <div className="absolute inset-0" style={{ background: PALETTES.ankara }} />
              <div className="absolute inset-0 grid place-items-center">
                <div className="rounded-2xl bg-black/55 px-5 py-4 text-center backdrop-blur-sm">
                  <Codicon name="device-camera" size="1.8rem" />
                  <div className="mt-2 text-sm font-semibold">Image analysed</div>
                  <div className="text-[0.6875rem] text-white/60">boutique_ankara_douala.jpg</div>
                </div>
              </div>
            </div>
            <div className={cn(CARD, 'p-5')}>
              <h4 className="flex items-center gap-2 text-sm font-semibold">
                <Codicon className="text-[#8B46FF]" name="sparkle" size="0.95rem" />
                Image description
              </h4>
              <p className="mt-2 text-sm leading-relaxed text-white/70">
                A boutique storefront in Douala displaying Ankara-fabric dresses with red and gold geometric patterns.
                Natural late-day lighting, lively market mood. Ideal as a cover photo for a fashion catalogue.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {['Fashion', 'Ankara', 'Douala', 'Retail', 'Golden light'].map(t => (
                  <span
                    className="rounded-full border border-[#8B46FF]/25 bg-[#8B46FF]/14 px-2.5 py-1 text-[0.6875rem] font-semibold text-[#c9b3ff]"
                    key={t}
                  >
                    {t}
                  </span>
                ))}
              </div>
              <div className="mt-4 flex gap-2">
                <button className="inline-flex h-8 items-center gap-2 rounded-lg border border-white/8 bg-white/[0.06] px-3 text-xs font-semibold" type="button">
                  <Codicon name="text-size" size="0.85rem" />
                  Alt text
                </button>
                <button className="inline-flex h-8 items-center gap-2 rounded-lg border border-white/8 bg-white/[0.06] px-3 text-xs font-semibold" type="button">
                  <Codicon name="comment" size="0.85rem" />
                  Social caption
                </button>
              </div>
            </div>
          </div>
        )}

        {/* TEXT FROM IMAGE */}
        {tab === 'txt' && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className={cn(CARD, 'relative min-h-[320px] overflow-hidden p-0')}>
              <div className="absolute inset-0" style={{ background: PALETTES.food }} />
              <div className="absolute inset-0 grid place-items-center">
                <div className="rounded-2xl bg-black/55 px-5 py-4 text-center backdrop-blur-sm">
                  <Codicon name="text-size" size="1.8rem" />
                  <div className="mt-2 text-sm font-semibold">Scanned receipt</div>
                  <div className="text-[0.6875rem] text-white/60">recu_marche_yaounde.jpg</div>
                </div>
              </div>
            </div>
            <div className={cn(CARD, 'p-5')}>
              <h4 className="flex items-center gap-2 text-sm font-semibold">
                <Codicon className="text-[#8B46FF]" name="text-size" size="0.95rem" />
                Extracted text
              </h4>
              <div className="mt-3 space-y-2 font-mono text-[0.72rem] leading-relaxed text-white/70">
                <div className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2.5">
                  <b className="text-white">DORAMNS ENTREPRISES</b>
                  <br />
                  Marché Mokolo, Yaoundé · Tél +237 6 99 88 77 66
                </div>
                <div className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2.5">
                  02× Sac de riz 25kg ........ 32 000 FCFA
                  <br />
                  05× Cartons d&apos;huile ...... 45 000 FCFA
                  <br />
                  01× Livraison Douala ...... 15 000 FCFA
                </div>
                <div className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2.5">
                  <b className="text-white">TOTAL ....... 92 000 FCFA</b> · Payé via Orange Money
                </div>
              </div>
              <div className="mt-4 flex gap-2">
                <button className="inline-flex h-8 items-center gap-2 rounded-lg border border-white/8 bg-white/[0.06] px-3 text-xs font-semibold" type="button">
                  <Codicon name="table" size="0.85rem" />
                  Export to table
                </button>
                <button className="inline-flex h-8 items-center gap-2 rounded-lg border border-white/8 bg-white/[0.06] px-3 text-xs font-semibold" type="button">
                  <Codicon name="copy" size="0.85rem" />
                  Copy
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
