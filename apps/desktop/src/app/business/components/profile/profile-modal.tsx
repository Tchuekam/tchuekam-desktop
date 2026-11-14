import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { Codicon } from '@/components/ui/codicon'
import { cn } from '@/lib/utils'
import { notify } from '@/store/notifications'

import {
  $businessProfile,
  $personalProfile,
  saveBusinessProfile,
  savePersonalProfile
} from '../../store'
import type { BusinessProfile, CurrencyCode, DocumentLanguage, PersonalProfile } from '../../types'

interface ProfileModalProps {
  onClose: () => void
  open: boolean
}

export function ProfileModal({ onClose, open }: ProfileModalProps) {
  const savedBiz = useStore($businessProfile)
  const savedPersonal = useStore($personalProfile)

  const [tab, setTab] = useState<'business' | 'personal'>('business')
  const [biz, setBiz] = useState<BusinessProfile>(() => ({ ...savedBiz }))
  const [personal, setPersonal] = useState<PersonalProfile>(() => ({ ...savedPersonal }))
  const [skillInput, setSkillInput] = useState(() => savedPersonal.skills.join(', '))

  // Keep state reactive and fresh whenever modal opens
  useEffect(() => {
    if (open) {
      setBiz({ ...savedBiz })
      setPersonal({ ...savedPersonal })
      setSkillInput(savedPersonal.skills.join(', '))
    }
  }, [open, savedBiz, savedPersonal])

  // Close on Escape key press
  useEffect(() => {
    if (!open) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  if (!open) {
    return null
  }

  const handleLogoUpload = (file: File | undefined) => {
    if (!file) {
      return
    }

    const reader = new FileReader()

    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setBiz(prev => ({ ...prev, logoDataUrl: reader.result as string }))
      }
    }

    reader.readAsDataURL(file)
  }

  const handleRemoveLogo = () => {
    setBiz(prev => ({ ...prev, logoDataUrl: '' }))
  }

  const handleSave = (event: React.FormEvent) => {
    event.preventDefault()
    saveBusinessProfile(biz)
    savePersonalProfile({
      ...personal,
      skills: skillInput
        .split(',')
        .map(s => s.trim())
        .filter(Boolean)
    })
    notify({
      kind: 'success',
      message: 'Business and personal profiles saved.',
      title: 'Profile updated'
    })
    onClose()
  }

  const inputClass =
    'w-full rounded-xl border border-border/70 bg-background/80 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 transition-all focus:border-primary focus:bg-background focus:outline-none focus:ring-2 focus:ring-primary/20'

  const labelClass = 'mb-1.5 block text-[0.6875rem] font-semibold text-muted-foreground tracking-wide'

  return (
    <div
      aria-label="Business & Personal Profiles"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2.5 backdrop-blur-md transition-opacity duration-200 sm:p-4"
      onClick={e => {
        if (e.target === e.currentTarget) {
          onClose()
        }
      }}
      role="dialog"
    >
      <div className="flex max-h-[90dvh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border/80 bg-card/95 text-foreground shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-muted/20 px-4 py-3 sm:px-6 sm:py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-xl bg-primary/10 text-primary">
              <Codicon name="settings-gear" size="1.1rem" />
            </div>
            <div>
              <h2 className="text-base font-semibold tracking-tight">Saved Profiles & Identity</h2>
              <p className="text-xs text-muted-foreground">
                Pre-fill your company details and CV information across all business templates.
              </p>
            </div>
          </div>
          <button
            aria-label="Close profile settings"
            className="rounded-lg p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
            onClick={onClose}
            type="button"
          >
            <Codicon name="close" size="1rem" />
          </button>
        </div>

        {/* Apple-style Segmented Control */}
        <div className="border-b border-border/60 bg-muted/10 px-4 py-2 sm:px-6 sm:py-2.5">
          <div className="inline-flex w-full flex-col gap-1 rounded-xl border border-border/40 bg-muted/60 p-1 sm:flex-row">
            <button
              className={cn(
                'flex flex-1 items-center justify-center gap-2 rounded-lg py-1.5 text-xs font-semibold transition-all duration-150',
                tab === 'business'
                  ? 'bg-card text-foreground shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              onClick={() => setTab('business')}
              type="button"
            >
              <Codicon name="briefcase" size="0.85rem" />
              Business Identity (Invoices, Quotes, Contracts)
            </button>
            <button
              className={cn(
                'flex flex-1 items-center justify-center gap-2 rounded-lg py-1.5 text-xs font-semibold transition-all duration-150',
                tab === 'personal'
                  ? 'bg-card text-foreground shadow-2xs'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              onClick={() => setTab('personal')}
              type="button"
            >
              <Codicon name="account" size="0.85rem" />
              Personal Profile (CV & Cover Letters)
            </button>
          </div>
        </div>

        <form className="flex min-h-0 flex-1 flex-col" onSubmit={handleSave}>
          <div className="flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
            {tab === 'business' ? (
              <>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label className={labelClass} htmlFor="biz-company-name">
                      Company Name
                    </label>
                    <input
                      className={inputClass}
                      id="biz-company-name"
                      onChange={e => setBiz({ ...biz, companyName: e.target.value })}
                      placeholder="e.g. TchueKAM SARL"
                      value={biz.companyName}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-logo-upload">
                      Company Logo (PNG / JPG)
                    </label>
                    {biz.logoDataUrl ? (
                      <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-background/50 p-2">
                        <img
                          alt="Uploaded logo preview"
                          className="h-8 max-w-[120px] rounded object-contain bg-white/10 p-0.5"
                          src={biz.logoDataUrl}
                        />
                        <div className="flex flex-1 items-center justify-between text-xs">
                          <span className="text-[0.6875rem] text-muted-foreground">Logo attached</span>
                          <button
                            className="rounded px-2 py-0.5 text-[0.6875rem] font-semibold text-destructive hover:bg-destructive/10"
                            onClick={handleRemoveLogo}
                            type="button"
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    ) : (
                      <input
                        accept="image/png,image/jpeg,image/webp"
                        className={inputClass}
                        id="biz-logo-upload"
                        onChange={e => handleLogoUpload(e.target.files?.[0])}
                        type="file"
                      />
                    )}
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-niu">
                      NIU (Tax Identification Number)
                    </label>
                    <input
                      className={inputClass}
                      id="biz-niu"
                      onChange={e => setBiz({ ...biz, niu: e.target.value })}
                      placeholder="M012345678901A"
                      value={biz.niu}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-rccm">
                      RCCM (Trade Registry)
                    </label>
                    <input
                      className={inputClass}
                      id="biz-rccm"
                      onChange={e => setBiz({ ...biz, rccm: e.target.value })}
                      placeholder="RC/DLA/2026/B/1234"
                      value={biz.rccm}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={labelClass} htmlFor="biz-address">
                      Street Address
                    </label>
                    <input
                      className={inputClass}
                      id="biz-address"
                      onChange={e => setBiz({ ...biz, address: e.target.value })}
                      placeholder="e.g. 142 Rue du Commerce, Bonanjo"
                      value={biz.address}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-city">
                      City
                    </label>
                    <input
                      className={inputClass}
                      id="biz-city"
                      onChange={e => setBiz({ ...biz, city: e.target.value })}
                      placeholder="Douala"
                      value={biz.city}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-country">
                      Country
                    </label>
                    <input
                      className={inputClass}
                      id="biz-country"
                      onChange={e => setBiz({ ...biz, country: e.target.value })}
                      placeholder="Cameroun"
                      value={biz.country}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-phone">
                      Telephone
                    </label>
                    <input
                      className={inputClass}
                      id="biz-phone"
                      onChange={e => setBiz({ ...biz, telephone: e.target.value })}
                      placeholder="+237 6XX XX XX XX"
                      value={biz.telephone}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-email">
                      Email
                    </label>
                    <input
                      className={inputClass}
                      id="biz-email"
                      onChange={e => setBiz({ ...biz, email: e.target.value })}
                      placeholder="billing@company.cm"
                      value={biz.email}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-currency">
                      Default Currency
                    </label>
                    <select
                      className={inputClass}
                      id="biz-currency"
                      onChange={e =>
                        setBiz({ ...biz, defaultCurrency: e.target.value as CurrencyCode })
                      }
                      value={biz.defaultCurrency}
                    >
                      <option value="XAF">FCFA (XAF)</option>
                      <option value="EUR">Euro (EUR)</option>
                      <option value="USD">US Dollar (USD)</option>
                    </select>
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-tax">
                      Default Tax / TVA (%)
                    </label>
                    <input
                      className={inputClass}
                      id="biz-tax"
                      onChange={e =>
                        setBiz({ ...biz, defaultTaxRate: parseFloat(e.target.value) || 0 })
                      }
                      step="0.01"
                      type="number"
                      value={biz.defaultTaxRate}
                    />
                  </div>
                </div>

                {/* Mobile Money & Banking Details Card */}
                <div className="rounded-2xl border border-border/70 bg-muted/20 p-4.5 space-y-3.5">
                  <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                    <Codicon name="credit-card" size="0.9rem" />
                    <span>Payment & Mobile Money Merchant Channels</span>
                  </div>
                  <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
                    <div>
                      <label className={labelClass} htmlFor="biz-momo-code">
                        MTN MoMo Number / Merchant Code
                      </label>
                      <input
                        className={inputClass}
                        id="biz-momo-code"
                        onChange={e => setBiz({ ...biz, momoMerchantCode: e.target.value })}
                        placeholder="*126*... or +237 67..."
                        value={biz.momoMerchantCode}
                      />
                    </div>
                    <div>
                      <label className={labelClass} htmlFor="biz-momo-name">
                        MTN MoMo Account Name
                      </label>
                      <input
                        className={inputClass}
                        id="biz-momo-name"
                        onChange={e => setBiz({ ...biz, momoAccountName: e.target.value })}
                        placeholder="Account name as registered on MoMo"
                        value={biz.momoAccountName}
                      />
                    </div>
                    <div>
                      <label className={labelClass} htmlFor="biz-om-code">
                        Orange Money Code / Number
                      </label>
                      <input
                        className={inputClass}
                        id="biz-om-code"
                        onChange={e => setBiz({ ...biz, orangeMoneyCode: e.target.value })}
                        placeholder="#150*... or +237 69..."
                        value={biz.orangeMoneyCode}
                      />
                    </div>
                    <div>
                      <label className={labelClass} htmlFor="biz-om-name">
                        Orange Money Account Name
                      </label>
                      <input
                        className={inputClass}
                        id="biz-om-name"
                        onChange={e => setBiz({ ...biz, orangeMoneyName: e.target.value })}
                        placeholder="Account name as registered on OM"
                        value={biz.orangeMoneyName}
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className={labelClass} htmlFor="biz-bank">
                        Bank Account / RIB / IBAN
                      </label>
                      <input
                        className={inputClass}
                        id="biz-bank"
                        onChange={e => setBiz({ ...biz, bankDetails: e.target.value })}
                        placeholder="Bank name — Code Banque / Guichet / Compte / Clé RIB"
                        value={biz.bankDetails}
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
                  <div>
                    <label className={labelClass} htmlFor="biz-signatory-name">
                      Authorized Signatory Name
                    </label>
                    <input
                      className={inputClass}
                      id="biz-signatory-name"
                      onChange={e => setBiz({ ...biz, signatoryName: e.target.value })}
                      placeholder="e.g. Rostand Tchuekam"
                      value={biz.signatoryName}
                    />
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="biz-signatory-title">
                      Signatory Title
                    </label>
                    <input
                      className={inputClass}
                      id="biz-signatory-title"
                      onChange={e => setBiz({ ...biz, signatoryTitle: e.target.value })}
                      placeholder="e.g. Managing Director"
                      value={biz.signatoryTitle}
                    />
                  </div>
                </div>
              </>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className={labelClass} htmlFor="pers-full-name">
                    Full Name
                  </label>
                  <input
                    className={inputClass}
                    id="pers-full-name"
                    onChange={e => setPersonal({ ...personal, fullName: e.target.value })}
                    placeholder="e.g. Rostand Tchuekam"
                    value={personal.fullName}
                  />
                </div>
                <div>
                  <label className={labelClass} htmlFor="pers-headline">
                    Professional Headline
                  </label>
                  <input
                    className={inputClass}
                    id="pers-headline"
                    onChange={e => setPersonal({ ...personal, headline: e.target.value })}
                    placeholder="e.g. Principal Systems Architect"
                    value={personal.headline}
                  />
                </div>
                <div>
                  <label className={labelClass} htmlFor="pers-email">
                    Email
                  </label>
                  <input
                    className={inputClass}
                    id="pers-email"
                    onChange={e => setPersonal({ ...personal, email: e.target.value })}
                    placeholder="rostand@tchuekam.com"
                    value={personal.email}
                  />
                </div>
                <div>
                  <label className={labelClass} htmlFor="pers-phone">
                    Phone
                  </label>
                  <input
                    className={inputClass}
                    id="pers-phone"
                    onChange={e => setPersonal({ ...personal, phone: e.target.value })}
                    placeholder="+237 6XX XX XX XX"
                    value={personal.phone}
                  />
                </div>
                <div>
                  <label className={labelClass} htmlFor="pers-location">
                    Location
                  </label>
                  <input
                    className={inputClass}
                    id="pers-location"
                    onChange={e => setPersonal({ ...personal, location: e.target.value })}
                    placeholder="Douala, Cameroun"
                    value={personal.location}
                  />
                </div>
                <div>
                  <label className={labelClass} htmlFor="pers-language">
                    Default Language
                  </label>
                  <select
                    className={inputClass}
                    id="pers-language"
                    onChange={e =>
                      setPersonal({
                        ...personal,
                        defaultLanguage: e.target.value as DocumentLanguage
                      })
                    }
                    value={personal.defaultLanguage}
                  >
                    <option value="fr">Français (FR)</option>
                    <option value="en">English (EN)</option>
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <label className={labelClass} htmlFor="pers-skills">
                    Core Skills (comma-separated)
                  </label>
                  <input
                    className={inputClass}
                    id="pers-skills"
                    onChange={e => setSkillInput(e.target.value)}
                    placeholder="Distributed Systems, FinOps, Cloud Architecture, Python, TypeScript"
                    value={skillInput}
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className={labelClass} htmlFor="pers-summary">
                    Professional Summary
                  </label>
                  <textarea
                    className={inputClass}
                    id="pers-summary"
                    onChange={e => setPersonal({ ...personal, summary: e.target.value })}
                    placeholder="Executive career summary..."
                    rows={4}
                    value={personal.summary}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Modal Footer */}
          <div className="flex flex-wrap items-center justify-end gap-2.5 border-t border-border/60 bg-muted/20 px-4 py-3 sm:px-6 sm:py-3.5">
            <button
              className="rounded-xl border border-border/70 bg-card px-4 py-2 text-xs font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground"
              onClick={onClose}
              type="button"
            >
              Cancel
            </button>
            <button
              className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-5 py-2 text-xs font-semibold text-primary-foreground shadow-sm transition hover:brightness-105 active:scale-[0.98]"
              type="submit"
            >
              <Codicon name="check" size="0.85rem" />
              Save Profile
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
