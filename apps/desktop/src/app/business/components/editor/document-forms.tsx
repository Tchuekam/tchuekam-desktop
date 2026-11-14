import { useStore } from '@nanostores/react'

import { Codicon } from '@/components/ui/codicon'
import { notify } from '@/store/notifications'

import type { BusinessAiOperation } from '../../services/ai-orchestrator'
import {
  $businessDocuments,
  $businessProfile,
  $personalProfile,
  createBusinessDocument
} from '../../store'
import type {
  AttestationCategory,
  AttestationData,
  BusinessDocument,
  BusinessPlanData,
  BusinessPlanSectionKey,
  ContractCategory,
  ContractData,
  CoverLetterData,
  CoverLetterTone,
  CurrencyCode,
  CVData,
  DocumentDataMap,
  DocumentType,
  InvoiceData,
  InvoicePaymentStatus,
  PaymentMethodType,
  PitchDeckData,
  PitchSlide,
  QuoteData,
  QuoteStatus,
  ScanDocumentData
} from '../../types'
import {
  analyzeCvAtsReadiness,
  auditContractWarnings,
  calculateBusinessPlanProjections,
  calculateLineItemsSummary,
  formatCurrency
} from '../../utils/calculations'

export interface DocumentFormsProps {
  activeSlideIndex: number
  aiBusy: string | null
  canUseAi: boolean
  document: BusinessDocument
  onConvertQuoteToInvoice: (quoteId: string) => void
  onReplaceScanFile: (file: File) => void
  onRunAi: (
    op: BusinessAiOperation,
    input: string,
    context: string,
    apply: (output: string, suggestions?: string[]) => void
  ) => void
  onSelectSlide: (idx: number) => void
  onUpdateData: <T extends DocumentType>(
    updater: (current: DocumentDataMap[T]) => DocumentDataMap[T]
  ) => void
}

const INPUT_CLASS =
  'h-8 w-full rounded-xl border border-border/70 bg-background/80 px-3 text-xs text-foreground placeholder:text-muted-foreground/60 transition-all focus:border-primary focus:bg-background focus:outline-none focus:ring-2 focus:ring-primary/20'

const TEXTAREA_CLASS =
  'w-full rounded-xl border border-border/70 bg-background/80 p-3 text-xs text-foreground placeholder:text-muted-foreground/60 transition-all focus:border-primary focus:bg-background focus:outline-none focus:ring-2 focus:ring-primary/20 leading-relaxed'

const LABEL_CLASS = 'mb-1.5 block text-[0.6875rem] font-semibold text-muted-foreground tracking-wide'
const SECTION_CARD = 'rounded-2xl border border-border/70 bg-card/85 p-3.5 shadow-xs backdrop-blur-sm space-y-3 sm:p-5 sm:space-y-3.5'

const PLAN_SECTION_LABELS: Array<{ key: BusinessPlanSectionKey; labelEn: string; labelFr: string }> = [
  { key: 'executiveSummary', labelEn: '1. Executive Summary', labelFr: '1. Résumé Exécutif' },
  { key: 'companyOverview', labelEn: '2. Company Overview', labelFr: '2. Présentation de l’Entreprise' },
  { key: 'problem', labelEn: '3. Problem Statement', labelFr: '3. Problématique Client' },
  { key: 'solution', labelEn: '4. Solution & Value Proposition', labelFr: '4. Solution & Proposition de Valeur' },
  { key: 'marketAnalysis', labelEn: '5. Market Analysis', labelFr: '5. Analyse du Marché' },
  { key: 'competitiveAnalysis', labelEn: '6. Competitive Analysis', labelFr: '6. Analyse Concurrentielle' },
  { key: 'productsServices', labelEn: '7. Products & Services', labelFr: '7. Produits & Services' },
  { key: 'businessModel', labelEn: '8. Business & Revenue Model', labelFr: '8. Modèle Économique' },
  { key: 'marketingStrategy', labelEn: '9. Marketing & Sales Strategy', labelFr: '9. Stratégie Marketing & Commerciale' },
  { key: 'operations', labelEn: '10. Operations Plan', labelFr: '10. Plan Opérationnel' },
  { key: 'managementTeam', labelEn: '11. Management Team', labelFr: '11. Équipe Dirigeante' },
  { key: 'financialProjections', labelEn: '12. Financial Narrative', labelFr: '12. Note Financière' },
  { key: 'fundingRequirements', labelEn: '13. Funding Requirements', labelFr: '13. Besoins de Financement' },
  { key: 'riskAnalysis', labelEn: '14. Risk Analysis & Mitigation', labelFr: '14. Analyse des Risques' }
]

export function DocumentForms({
  activeSlideIndex,
  aiBusy,
  canUseAi,
  document: doc,
  onConvertQuoteToInvoice,
  onReplaceScanFile,
  onRunAi,
  onSelectSlide,
  onUpdateData
}: DocumentFormsProps) {
  const allDocs = useStore($businessDocuments)
  const bizProfile = useStore($businessProfile)
  const personalProfile = useStore($personalProfile)

  if (doc.type === 'cv') {
    const cv = doc.data as CVData
    const ats = analyzeCvAtsReadiness(cv)

    const applyPersonalProfile = () => {
      onUpdateData<'cv'>(current => ({
        ...current,
        email: personalProfile.email || current.email,
        fullName: personalProfile.fullName || current.fullName,
        headline: personalProfile.headline || current.headline,
        linkedin: personalProfile.linkedin || current.linkedin,
        location: personalProfile.location || current.location,
        phone: personalProfile.phone || current.phone,
        skills: personalProfile.skills.length > 0 ? [...personalProfile.skills] : current.skills,
        summary: personalProfile.summary || current.summary,
        website: personalProfile.website || current.website
      }))
      notify({
        kind: 'success',
        message: 'Personal profile details applied to CV.',
        title: 'Profile applied'
      })
    }

    const moveSection = (index: number, direction: -1 | 1) => {
      const targetIndex = index + direction

      if (targetIndex < 0 || targetIndex >= cv.sectionOrder.length) {
        return
      }

      onUpdateData<'cv'>(current => {
        const nextOrder = [...current.sectionOrder]
        const temp = nextOrder[index]
        const swap = nextOrder[targetIndex]

        if (temp && swap) {
          nextOrder[index] = swap
          nextOrder[targetIndex] = temp
        }

        return { ...current, sectionOrder: nextOrder }
      })
    }

    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-primary/25 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent p-4 shadow-2xs backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-white shadow-xs">
              <span className="text-xs font-bold">{ats.score}</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-foreground">ATS Readiness Score</span>
                <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[0.625rem] font-bold text-primary">
                  {ats.score >= 80 ? 'Optimal' : ats.score >= 50 ? 'Good' : 'Needs Review'}
                </span>
              </div>
              <div className="mt-0.5 text-[0.6875rem] text-muted-foreground">
                {ats.checks.every(c => c.passed)
                  ? 'All core ATS structural checks passed.'
                  : ats.checks
                      .filter(c => !c.passed)
                      .map(c => c.label)
                      .join(' · ')}
              </div>
            </div>
          </div>
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-border/80 bg-card px-3 text-xs font-semibold text-foreground shadow-2xs transition hover:border-primary/40 hover:bg-muted"
            onClick={applyPersonalProfile}
            type="button"
          >
            <Codicon name="account" size="0.85rem" />
            Apply Saved Personal Profile
          </button>
        </div>

        {/* Contact & Identity */}
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Personal Details</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLASS} htmlFor="cv-fullname">Full Name</label>
              <input
                aria-label="Full Name"
                className={INPUT_CLASS}
                id="cv-fullname"
                onChange={e => onUpdateData<'cv'>(c => ({ ...c, fullName: e.target.value }))}
                value={cv.fullName}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="cv-headline">Professional Headline</label>
              <input
                aria-label="Professional Headline"
                className={INPUT_CLASS}
                id="cv-headline"
                onChange={e => onUpdateData<'cv'>(c => ({ ...c, headline: e.target.value }))}
                value={cv.headline}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="cv-email">Email</label>
              <input
                aria-label="Email"
                className={INPUT_CLASS}
                id="cv-email"
                onChange={e => onUpdateData<'cv'>(c => ({ ...c, email: e.target.value }))}
                value={cv.email}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="cv-phone">Phone</label>
              <input
                aria-label="Phone"
                className={INPUT_CLASS}
                id="cv-phone"
                onChange={e => onUpdateData<'cv'>(c => ({ ...c, phone: e.target.value }))}
                value={cv.phone}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="cv-location">Location</label>
              <input
                aria-label="Location"
                className={INPUT_CLASS}
                id="cv-location"
                onChange={e => onUpdateData<'cv'>(c => ({ ...c, location: e.target.value }))}
                value={cv.location}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="cv-linkedin">LinkedIn / Portfolio</label>
              <input
                aria-label="LinkedIn"
                className={INPUT_CLASS}
                id="cv-linkedin"
                onChange={e => onUpdateData<'cv'>(c => ({ ...c, linkedin: e.target.value }))}
                value={cv.linkedin}
              />
            </div>
          </div>
        </section>

        {/* Professional Summary */}
        <section className={SECTION_CARD}>
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold uppercase tracking-wider text-foreground" htmlFor="cv-summary">
              Professional Summary
            </label>
            <button
              className="inline-flex h-7 items-center gap-1 rounded-lg bg-primary/10 px-2.5 text-[0.6875rem] font-semibold text-primary hover:bg-primary/20 disabled:opacity-50"
              disabled={!canUseAi || aiBusy !== null}
              onClick={() =>
                onRunAi('improve_summary', cv.summary, cv.headline, output =>
                  onUpdateData<'cv'>(c => ({ ...c, summary: output }))
                )
              }
              type="button"
            >
              <Codicon name="sparkle" size="0.75rem" />
              {aiBusy === 'improve_summary' ? 'Improving...' : 'AI Improve Summary'}
            </button>
          </div>
          <textarea
            aria-label="Professional Summary"
            className={TEXTAREA_CLASS}
            id="cv-summary"
            onChange={e => onUpdateData<'cv'>(c => ({ ...c, summary: e.target.value }))}
            rows={3}
            value={cv.summary}
          />
        </section>

        {/* Job Targeting & ATS Keyword Matcher */}
        <section className={SECTION_CARD}>
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold uppercase tracking-wider text-foreground" htmlFor="cv-target-job">
              Target Job Description (ATS Tailoring)
            </label>
            <button
              className="inline-flex h-7 items-center gap-1 rounded-lg bg-primary/10 px-2.5 text-[0.6875rem] font-semibold text-primary hover:bg-primary/20 disabled:opacity-50"
              disabled={!canUseAi || aiBusy !== null || !cv.targetJobDescription.trim()}
              onClick={() =>
                onRunAi('tailor_to_job', cv.summary, cv.targetJobDescription, output =>
                  onUpdateData<'cv'>(c => ({ ...c, summary: output }))
                )
              }
              type="button"
            >
              <Codicon name="sparkle" size="0.75rem" />
              AI Tailor to Job
            </button>
          </div>
          <textarea
            aria-label="Target Job Description"
            className={TEXTAREA_CLASS}
            id="cv-target-job"
            onChange={e => onUpdateData<'cv'>(c => ({ ...c, targetJobDescription: e.target.value }))}
            placeholder="Paste a job posting here to check keyword alignment..."
            rows={2}
            value={cv.targetJobDescription}
          />
          {ats.missingKeywords.length > 0 && (
            <div className="text-[0.6875rem] text-amber-600 dark:text-amber-400">
              Missing keywords from job description: {ats.missingKeywords.slice(0, 8).join(', ')}
            </div>
          )}
        </section>

        {/* Work Experience */}
        <section className={SECTION_CARD}>
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Work Experience</h3>
            <button
              className="inline-flex h-7 items-center gap-1 rounded-lg border border-border px-2.5 text-xs font-semibold hover:border-primary/40"
              onClick={() =>
                onUpdateData<'cv'>(c => ({
                  ...c,
                  experience: [
                    ...c.experience,
                    {
                      achievements: ['Key achievement [to confirm]'],
                      company: 'Company [to confirm]',
                      current: false,
                      endDate: '2025',
                      id: `exp-${Date.now()}`,
                      location: c.location || 'Douala',
                      role: 'Role Title [to confirm]',
                      startDate: '2023'
                    }
                  ]
                }))
              }
              type="button"
            >
              <Codicon name="add" size="0.75rem" />
              Add Experience
            </button>
          </div>
          <div className="space-y-3">
            {cv.experience.map((exp, idx) => (
              <div className="rounded-lg border border-border/70 bg-background/60 p-3 space-y-2.5" key={exp.id}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold">Position #{idx + 1}</span>
                  <div className="flex items-center gap-1.5">
                    <button
                      className="inline-flex h-6 items-center gap-1 rounded bg-primary/10 px-2 text-[0.6875rem] font-semibold text-primary disabled:opacity-50"
                      disabled={!canUseAi || aiBusy !== null}
                      onClick={() =>
                        onRunAi(
                          'enhance_bullets',
                          exp.achievements.join('\n'),
                          exp.role,
                          output =>
                            onUpdateData<'cv'>(c => ({
                              ...c,
                              experience: c.experience.map(item =>
                                item.id === exp.id
                                  ? {
                                      ...item,
                                      achievements: output
                                        .split(/\r?\n/)
                                        .map(l => l.trim())
                                        .filter(Boolean)
                                    }
                                  : item
                              )
                            }))
                        )
                      }
                      type="button"
                    >
                      <Codicon name="sparkle" size="0.7rem" />
                      AI Enhance Bullets
                    </button>
                    {cv.experience.length > 1 && (
                      <button
                        aria-label={`Remove Experience ${idx + 1}`}
                        className="inline-flex h-6 items-center rounded px-1.5 text-xs text-muted-foreground hover:text-destructive"
                        onClick={() =>
                          onUpdateData<'cv'>(c => ({
                            ...c,
                            experience: c.experience.filter(item => item.id !== exp.id)
                          }))
                        }
                        type="button"
                      >
                        <Codicon name="trash" size="0.75rem" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <input
                    aria-label={`Experience Role ${idx + 1}`}
                    className={INPUT_CLASS}
                    onChange={e =>
                      onUpdateData<'cv'>(c => ({
                        ...c,
                        experience: c.experience.map(item =>
                          item.id === exp.id ? { ...item, role: e.target.value } : item
                        )
                      }))
                    }
                    placeholder="Role / Job Title"
                    value={exp.role}
                  />
                  <input
                    aria-label={`Experience Company ${idx + 1}`}
                    className={INPUT_CLASS}
                    onChange={e =>
                      onUpdateData<'cv'>(c => ({
                        ...c,
                        experience: c.experience.map(item =>
                          item.id === exp.id ? { ...item, company: e.target.value } : item
                        )
                      }))
                    }
                    placeholder="Company"
                    value={exp.company}
                  />
                  <input
                    aria-label={`Experience Start Date ${idx + 1}`}
                    className={INPUT_CLASS}
                    onChange={e =>
                      onUpdateData<'cv'>(c => ({
                        ...c,
                        experience: c.experience.map(item =>
                          item.id === exp.id ? { ...item, startDate: e.target.value } : item
                        )
                      }))
                    }
                    placeholder="Start Date (e.g. 2023-01)"
                    value={exp.startDate}
                  />
                  <input
                    aria-label={`Experience End Date ${idx + 1}`}
                    className={INPUT_CLASS}
                    onChange={e =>
                      onUpdateData<'cv'>(c => ({
                        ...c,
                        experience: c.experience.map(item =>
                          item.id === exp.id ? { ...item, endDate: e.target.value } : item
                        )
                      }))
                    }
                    placeholder="End Date (or Present)"
                    value={exp.endDate}
                  />
                </div>
                <textarea
                  aria-label={`Experience Achievements ${idx + 1}`}
                  className={TEXTAREA_CLASS}
                  onChange={e =>
                    onUpdateData<'cv'>(c => ({
                      ...c,
                      experience: c.experience.map(item =>
                        item.id === exp.id
                          ? { ...item, achievements: e.target.value.split(/\r?\n/) }
                          : item
                      )
                    }))
                  }
                  placeholder="One achievement bullet per line..."
                  rows={3}
                  value={exp.achievements.join('\n')}
                />
              </div>
            ))}
          </div>
        </section>

        {/* Education */}
        <section className={SECTION_CARD}>
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Education</h3>
            <button
              className="inline-flex h-7 items-center gap-1 rounded-lg border border-border px-2.5 text-xs font-semibold hover:border-primary/40"
              onClick={() =>
                onUpdateData<'cv'>(c => ({
                  ...c,
                  education: [
                    ...c.education,
                    {
                      degree: 'Degree [to confirm]',
                      endDate: '2024',
                      field: 'Field of Study',
                      honors: '',
                      id: `edu-${Date.now()}`,
                      institution: 'Institution [to confirm]',
                      location: c.location || 'Douala',
                      startDate: '2021'
                    }
                  ]
                }))
              }
              type="button"
            >
              <Codicon name="add" size="0.75rem" />
              Add Education
            </button>
          </div>
          {cv.education.map((edu, idx) => (
            <div className="grid grid-cols-1 gap-2.5 rounded-xl border border-border/70 bg-background/50 p-3 sm:grid-cols-2" key={edu.id}>
              <div className="flex items-center justify-between sm:col-span-2">
                <span className="text-[0.6875rem] font-semibold text-muted-foreground">Education Entry #{idx + 1}</span>
                <button
                  aria-label={`Remove Education ${idx + 1}`}
                  className="rounded-lg p-1 text-muted-foreground transition hover:bg-muted hover:text-destructive"
                  onClick={() =>
                    onUpdateData<'cv'>(c => ({
                      ...c,
                      education: c.education.filter(item => item.id !== edu.id)
                    }))
                  }
                  type="button"
                >
                  <Codicon name="trash" size="0.75rem" />
                </button>
              </div>
              <input
                aria-label={`Education Degree ${idx + 1}`}
                className={INPUT_CLASS}
                onChange={e =>
                  onUpdateData<'cv'>(c => ({
                    ...c,
                    education: c.education.map(item =>
                      item.id === edu.id ? { ...item, degree: e.target.value } : item
                    )
                  }))
                }
                placeholder="Degree"
                value={edu.degree}
              />
              <input
                aria-label={`Education Institution ${idx + 1}`}
                className={INPUT_CLASS}
                onChange={e =>
                  onUpdateData<'cv'>(c => ({
                    ...c,
                    education: c.education.map(item =>
                      item.id === edu.id ? { ...item, institution: e.target.value } : item
                    )
                  }))
                }
                placeholder="Institution"
                value={edu.institution}
              />
              <input
                aria-label={`Education Field ${idx + 1}`}
                className={INPUT_CLASS}
                onChange={e =>
                  onUpdateData<'cv'>(c => ({
                    ...c,
                    education: c.education.map(item =>
                      item.id === edu.id ? { ...item, field: e.target.value } : item
                    )
                  }))
                }
                placeholder="Field of study"
                value={edu.field}
              />
              <input
                aria-label={`Education End Year ${idx + 1}`}
                className={INPUT_CLASS}
                onChange={e =>
                  onUpdateData<'cv'>(c => ({
                    ...c,
                    education: c.education.map(item =>
                      item.id === edu.id ? { ...item, endDate: e.target.value } : item
                    )
                  }))
                }
                placeholder="Graduation Year"
                value={edu.endDate}
              />
            </div>
          ))}
        </section>

        {/* Skills */}
        <section className={SECTION_CARD}>
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold uppercase tracking-wider text-foreground" htmlFor="cv-skills">
              Core Skills (comma-separated)
            </label>
            <button
              className="inline-flex h-7 items-center gap-1 rounded-lg bg-primary/10 px-2.5 text-[0.6875rem] font-semibold text-primary hover:bg-primary/20 disabled:opacity-50"
              disabled={!canUseAi || aiBusy !== null}
              onClick={() =>
                onRunAi('suggest_skills', cv.headline, cv.summary, (_output, suggestions) => {
                  const nextSkills = suggestions && suggestions.length > 0 ? suggestions : []

                  if (nextSkills.length > 0) {
                    onUpdateData<'cv'>(c => ({
                      ...c,
                      skills: Array.from(new Set([...c.skills, ...nextSkills]))
                    }))
                  }
                })
              }
              type="button"
            >
              <Codicon name="sparkle" size="0.75rem" />
              AI Suggest Skills
            </button>
          </div>
          <input
            aria-label="Core Skills"
            className={INPUT_CLASS}
            id="cv-skills"
            onChange={e =>
              onUpdateData<'cv'>(c => ({
                ...c,
                skills: e.target.value
                  .split(',')
                  .map(s => s.trim())
                  .filter(Boolean)
              }))
            }
            value={cv.skills.join(', ')}
          />
        </section>

        {/* Section Order Controls */}
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
            Section Order (Reorder CV Layout)
          </h3>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {cv.sectionOrder.map((sec, idx) => (
              <div
                className="flex items-center justify-between rounded-lg border border-border/70 bg-background px-2.5 py-1.5 text-xs"
                key={sec}
              >
                <span className="font-medium capitalize">{sec}</span>
                <div className="flex items-center gap-1">
                  <button
                    aria-label={`Move ${sec} up`}
                    className="rounded p-1 hover:bg-muted disabled:opacity-30"
                    disabled={idx === 0}
                    onClick={() => moveSection(idx, -1)}
                    type="button"
                  >
                    <Codicon name="arrow-up" size="0.75rem" />
                  </button>
                  <button
                    aria-label={`Move ${sec} down`}
                    className="rounded p-1 hover:bg-muted disabled:opacity-30"
                    disabled={idx === cv.sectionOrder.length - 1}
                    onClick={() => moveSection(idx, 1)}
                    type="button"
                  >
                    <Codicon name="arrow-down" size="0.75rem" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    )
  }

  if (doc.type === 'invoice' || doc.type === 'quote') {
    const isQuote = doc.type === 'quote'
    const inv = doc.data as InvoiceData & QuoteData
    const summary = calculateLineItemsSummary(inv.items, isQuote ? 0 : inv.amountPaid)

    const applyBusinessProfile = () => {
      const paymentLines: string[] = []

      if (bizProfile.momoMerchantCode) {
        paymentLines.push(
          `MTN MoMo: ${bizProfile.momoMerchantCode} (${bizProfile.momoAccountName || bizProfile.companyName})`
        )
      }

      if (bizProfile.orangeMoneyCode) {
        paymentLines.push(
          `Orange Money: ${bizProfile.orangeMoneyCode} (${bizProfile.orangeMoneyName || bizProfile.companyName})`
        )
      }

      if (bizProfile.bankDetails) {
        paymentLines.push(`Banque: ${bizProfile.bankDetails}`)
      }

      const updateSeller = {
        address: [bizProfile.address, bizProfile.city, bizProfile.country].filter(Boolean).join(', '),
        companyName: bizProfile.companyName || inv.seller.companyName,
        email: bizProfile.email || inv.seller.email,
        logoDataUrl: bizProfile.logoDataUrl || inv.seller.logoDataUrl,
        niu: bizProfile.niu || inv.seller.niu,
        phone: bizProfile.telephone || inv.seller.phone,
        rccm: bizProfile.rccm || inv.seller.rccm
      }

      if (isQuote) {
        onUpdateData<'quote'>(c => ({
          ...c,
          currency: bizProfile.defaultCurrency || c.currency,
          paymentDetails: paymentLines.join(' · ') || c.paymentDetails,
          seller: updateSeller,
          signatoryName: bizProfile.signatoryName || c.signatoryName
        }))
      } else {
        onUpdateData<'invoice'>(c => ({
          ...c,
          currency: bizProfile.defaultCurrency || c.currency,
          paymentDetails: paymentLines.join(' · ') || c.paymentDetails,
          seller: updateSeller,
          signatoryName: bizProfile.signatoryName || c.signatoryName
        }))
      }

      notify({
        kind: 'success',
        message: 'Saved Business Profile applied to seller & payment fields.',
        title: 'Business Profile Applied'
      })
    }

    const updateShared = (updater: (current: InvoiceData & QuoteData) => InvoiceData & QuoteData) => {
      if (isQuote) {
        onUpdateData<'quote'>(c => updater(c as InvoiceData & QuoteData))
      } else {
        onUpdateData<'invoice'>(c => updater(c as InvoiceData & QuoteData))
      }
    }

    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card px-3.5 py-2.5">
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-semibold hover:border-primary/40"
            onClick={applyBusinessProfile}
            type="button"
          >
            <Codicon name="briefcase" size="0.8rem" />
            Apply Saved Business Profile
          </button>

          {isQuote && (
            <button
              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[#17694D] px-3 text-xs font-semibold text-white shadow-xs hover:brightness-105"
              onClick={() => onConvertQuoteToInvoice(doc.id)}
              type="button"
            >
              <Codicon name="arrow-swap" size="0.8rem" />
              Convert to Invoice
            </button>
          )}
        </div>

        {/* Metadata */}
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
            {isQuote ? 'Quotation Details' : 'Invoice Details'}
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className={LABEL_CLASS} htmlFor="doc-number">
                {isQuote ? 'Quote Number' : 'Invoice Number'}
              </label>
              <input
                aria-label={isQuote ? 'Quote Number' : 'Invoice Number'}
                className={INPUT_CLASS}
                id="doc-number"
                onChange={e =>
                  updateShared(c =>
                    isQuote
                      ? { ...c, quoteNumber: e.target.value }
                      : { ...c, invoiceNumber: e.target.value }
                  )
                }
                value={isQuote ? inv.quoteNumber : inv.invoiceNumber}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="doc-issue-date">Issue Date</label>
              <input
                aria-label="Issue Date"
                className={INPUT_CLASS}
                id="doc-issue-date"
                onChange={e => updateShared(c => ({ ...c, issueDate: e.target.value }))}
                type="date"
                value={inv.issueDate}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="doc-due-date">
                {isQuote ? 'Valid Until' : 'Due Date'}
              </label>
              <input
                aria-label={isQuote ? 'Valid Until' : 'Due Date'}
                className={INPUT_CLASS}
                id="doc-due-date"
                onChange={e =>
                  updateShared(c =>
                    isQuote
                      ? { ...c, validUntil: e.target.value }
                      : { ...c, dueDate: e.target.value }
                  )
                }
                type="date"
                value={isQuote ? inv.validUntil : inv.dueDate}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="doc-currency">Currency</label>
              <select
                aria-label="Currency"
                className={INPUT_CLASS}
                id="doc-currency"
                onChange={e => updateShared(c => ({ ...c, currency: e.target.value as CurrencyCode }))}
                value={inv.currency}
              >
                <option value="XAF">FCFA (XAF)</option>
                <option value="EUR">EUR (€)</option>
                <option value="USD">USD ($)</option>
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="doc-status">Status</label>
              {isQuote ? (
                <select
                  aria-label="Status"
                  className={INPUT_CLASS}
                  id="doc-status"
                  onChange={e => updateShared(c => ({ ...c, status: e.target.value as QuoteStatus }))}
                  value={inv.status}
                >
                  <option value="draft">Draft</option>
                  <option value="sent">Sent</option>
                  <option value="accepted">Accepted</option>
                  <option value="declined">Declined</option>
                </select>
              ) : (
                <select
                  aria-label="Status"
                  className={INPUT_CLASS}
                  id="doc-status"
                  onChange={e =>
                    updateShared(c => ({ ...c, paymentStatus: e.target.value as InvoicePaymentStatus }))
                  }
                  value={inv.paymentStatus}
                >
                  <option value="draft">Draft</option>
                  <option value="unpaid">Unpaid</option>
                  <option value="partially_paid">Partially Paid</option>
                  <option value="paid">Paid</option>
                  <option value="overdue">Overdue</option>
                </select>
              )}
            </div>
            {!isQuote && (
              <div>
                <label className={LABEL_CLASS} htmlFor="doc-amount-paid">Amount Paid</label>
                <input
                  aria-label="Amount Paid"
                  className={INPUT_CLASS}
                  id="doc-amount-paid"
                  min={0}
                  onChange={e => updateShared(c => ({ ...c, amountPaid: Number(e.target.value) || 0 }))}
                  type="number"
                  value={inv.amountPaid}
                />
              </div>
            )}
          </div>
        </section>

        {/* Seller & Client */}
        <section className={SECTION_CARD}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">Seller (Issuer)</h4>
              <input
                aria-label="Seller Company Name"
                className={INPUT_CLASS}
                onChange={e =>
                  updateShared(c => ({ ...c, seller: { ...c.seller, companyName: e.target.value } }))
                }
                placeholder="Seller Company Name"
                value={inv.seller.companyName}
              />
              <input
                aria-label="Seller Address"
                className={INPUT_CLASS}
                onChange={e =>
                  updateShared(c => ({ ...c, seller: { ...c.seller, address: e.target.value } }))
                }
                placeholder="Seller Address"
                value={inv.seller.address}
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  aria-label="Seller NIU"
                  className={INPUT_CLASS}
                  onChange={e =>
                    updateShared(c => ({ ...c, seller: { ...c.seller, niu: e.target.value } }))
                  }
                  placeholder="NIU"
                  value={inv.seller.niu}
                />
                <input
                  aria-label="Seller RCCM"
                  className={INPUT_CLASS}
                  onChange={e =>
                    updateShared(c => ({ ...c, seller: { ...c.seller, rccm: e.target.value } }))
                  }
                  placeholder="RCCM"
                  value={inv.seller.rccm}
                />
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">Client (Recipient)</h4>
              <input
                aria-label="Client Company Name"
                className={INPUT_CLASS}
                onChange={e =>
                  updateShared(c => ({ ...c, client: { ...c.client, companyName: e.target.value } }))
                }
                placeholder="Client Company Name"
                value={inv.client.companyName}
              />
              <input
                aria-label="Client Contact Name"
                className={INPUT_CLASS}
                onChange={e =>
                  updateShared(c => ({ ...c, client: { ...c.client, name: e.target.value } }))
                }
                placeholder="Client Contact Name"
                value={inv.client.name}
              />
              <input
                aria-label="Client Address"
                className={INPUT_CLASS}
                onChange={e =>
                  updateShared(c => ({ ...c, client: { ...c.client, address: e.target.value } }))
                }
                placeholder="Client Address"
                value={inv.client.address}
              />
            </div>
          </div>
        </section>

        {/* Line Items */}
        <section className={SECTION_CARD}>
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Line Items</h3>
            <button
              className="inline-flex h-7 items-center gap-1 rounded-lg border border-border px-2.5 text-xs font-semibold hover:border-primary/40"
              onClick={() =>
                updateShared(c => ({
                  ...c,
                  items: [
                    ...c.items,
                    {
                      description: 'New service item',
                      discountPercent: 0,
                      id: `item-${Date.now()}-${c.items.length}`,
                      optional: false,
                      quantity: 1,
                      selected: true,
                      taxRatePercent: bizProfile.defaultTaxRate ?? 19.25,
                      unitPrice: c.currency === 'XAF' ? 50_000 : 100
                    }
                  ]
                }))
              }
              type="button"
            >
              <Codicon name="add" size="0.75rem" />
              Add Line Item
            </button>
          </div>

          <div className="space-y-2.5">
            {inv.items.map((item, idx) => (
              <div className="rounded-lg border border-border/70 bg-background/60 p-2.5 space-y-2" key={item.id}>
                <div className="flex items-center justify-between gap-2">
                  <input
                    aria-label={`Line Item Description ${idx + 1}`}
                    className={INPUT_CLASS}
                    onChange={e =>
                      updateShared(c => ({
                        ...c,
                        items: c.items.map(it =>
                          it.id === item.id ? { ...it, description: e.target.value } : it
                        )
                      }))
                    }
                    placeholder="Item description"
                    value={item.description}
                  />
                  {inv.items.length > 1 && (
                    <button
                      aria-label={`Remove Line Item ${idx + 1}`}
                      className="rounded p-1.5 text-muted-foreground hover:text-destructive"
                      onClick={() =>
                        updateShared(c => ({
                          ...c,
                          items: c.items.filter(it => it.id !== item.id)
                        }))
                      }
                      type="button"
                    >
                      <Codicon name="trash" size="0.8rem" />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <div>
                    <label className={LABEL_CLASS}>Qty</label>
                    <input
                      aria-label={`Line Item Quantity ${idx + 1}`}
                      className={INPUT_CLASS}
                      min={0}
                      onChange={e =>
                        updateShared(c => ({
                          ...c,
                          items: c.items.map(it =>
                            it.id === item.id ? { ...it, quantity: Number(e.target.value) || 0 } : it
                          )
                        }))
                      }
                      step="any"
                      type="number"
                      value={item.quantity}
                    />
                  </div>
                  <div>
                    <label className={LABEL_CLASS}>Unit Price</label>
                    <input
                      aria-label={`Line Item Unit Price ${idx + 1}`}
                      className={INPUT_CLASS}
                      min={0}
                      onChange={e =>
                        updateShared(c => ({
                          ...c,
                          items: c.items.map(it =>
                            it.id === item.id ? { ...it, unitPrice: Number(e.target.value) || 0 } : it
                          )
                        }))
                      }
                      step="any"
                      type="number"
                      value={item.unitPrice}
                    />
                  </div>
                  <div>
                    <label className={LABEL_CLASS}>Discount %</label>
                    <input
                      aria-label={`Line Item Discount ${idx + 1}`}
                      className={INPUT_CLASS}
                      max={100}
                      min={0}
                      onChange={e =>
                        updateShared(c => ({
                          ...c,
                          items: c.items.map(it =>
                            it.id === item.id
                              ? { ...it, discountPercent: Number(e.target.value) || 0 }
                              : it
                          )
                        }))
                      }
                      step="any"
                      type="number"
                      value={item.discountPercent}
                    />
                  </div>
                  <div>
                    <label className={LABEL_CLASS}>Tax %</label>
                    <input
                      aria-label={`Line Item Tax ${idx + 1}`}
                      className={INPUT_CLASS}
                      min={0}
                      onChange={e =>
                        updateShared(c => ({
                          ...c,
                          items: c.items.map(it =>
                            it.id === item.id
                              ? { ...it, taxRatePercent: Number(e.target.value) || 0 }
                              : it
                          )
                        }))
                      }
                      step="any"
                      type="number"
                      value={item.taxRatePercent}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Deterministic Totals Summary */}
          <div className="rounded-lg bg-muted/40 p-3 text-xs space-y-1">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal:</span>
              <span className="font-semibold">{formatCurrency(summary.subtotal, inv.currency, doc.language)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Discount:</span>
              <span>-{formatCurrency(summary.discountTotal, inv.currency, doc.language)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tax (TVA):</span>
              <span>{formatCurrency(summary.taxTotal, inv.currency, doc.language)}</span>
            </div>
            <div className="flex justify-between border-t border-border pt-1.5 text-sm font-bold text-primary">
              <span>Grand Total:</span>
              <span data-testid="financial-grand-total">
                {formatCurrency(summary.grandTotal, inv.currency, doc.language)}
              </span>
            </div>
            {!isQuote && (
              <div className="flex justify-between text-xs font-semibold">
                <span>Balance Due:</span>
                <span>{formatCurrency(summary.balanceDue, inv.currency, doc.language)}</span>
              </div>
            )}
          </div>
        </section>

        {/* Payment Details */}
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
            Payment & Signatory
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLASS} htmlFor="doc-payment-method">Payment Method</label>
              <select
                aria-label="Payment Method"
                className={INPUT_CLASS}
                id="doc-payment-method"
                onChange={e =>
                  updateShared(c => ({ ...c, paymentMethod: e.target.value as PaymentMethodType }))
                }
                value={inv.paymentMethod}
              >
                <option value="momo">MTN Mobile Money (MoMo)</option>
                <option value="orange_money">Orange Money</option>
                <option value="bank_transfer">Bank Transfer / Virement</option>
                <option value="cash">Cash / Espèces</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="doc-signatory">Signatory Name</label>
              <input
                aria-label="Signatory Name"
                className={INPUT_CLASS}
                id="doc-signatory"
                onChange={e => updateShared(c => ({ ...c, signatoryName: e.target.value }))}
                value={inv.signatoryName}
              />
            </div>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="doc-payment-details">
              Payment Coordinates (MoMo / Orange Money / IBAN)
            </label>
            <input
              aria-label="Payment Coordinates"
              className={INPUT_CLASS}
              id="doc-payment-details"
              onChange={e => updateShared(c => ({ ...c, paymentDetails: e.target.value }))}
              value={inv.paymentDetails}
            />
          </div>
        </section>
      </div>
    )
  }

  if (doc.type === 'contract') {
    const contract = doc.data as ContractData
    const warnings = auditContractWarnings(contract)

    return (
      <div className="space-y-4">
        {warnings.length > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-300 space-y-1">
            <div className="font-bold">Legal Review & Grounding Checks ({warnings.length})</div>
            <ul className="list-disc pl-4 space-y-0.5 text-[0.6875rem]">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Contract Metadata</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLASS} htmlFor="contract-category">Contract Category</label>
              <select
                aria-label="Contract Category"
                className={INPUT_CLASS}
                id="contract-category"
                onChange={e =>
                  onUpdateData<'contract'>(c => ({
                    ...c,
                    category: e.target.value as ContractCategory
                  }))
                }
                value={contract.category}
              >
                <option value="service">Service Agreement (Prestation)</option>
                <option value="employment">Employment Contract (Travail)</option>
                <option value="nda">Non-Disclosure Agreement (NDA)</option>
                <option value="lease">Commercial Lease (Bail)</option>
                <option value="consulting">Consulting Agreement</option>
                <option value="partnership">Partnership Agreement</option>
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="contract-effective-date">Effective Date</label>
              <input
                aria-label="Effective Date"
                className={INPUT_CLASS}
                id="contract-effective-date"
                onChange={e => onUpdateData<'contract'>(c => ({ ...c, effectiveDate: e.target.value }))}
                type="date"
                value={contract.effectiveDate}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="contract-party-a">Party A (Provider / Employer)</label>
              <input
                aria-label="Party A Name"
                className={INPUT_CLASS}
                id="contract-party-a"
                onChange={e => onUpdateData<'contract'>(c => ({ ...c, partyAName: e.target.value }))}
                value={contract.partyAName}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="contract-party-b">Party B (Client / Counterparty)</label>
              <input
                aria-label="Party B Name"
                className={INPUT_CLASS}
                id="contract-party-b"
                onChange={e => onUpdateData<'contract'>(c => ({ ...c, partyBName: e.target.value }))}
                value={contract.partyBName}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="contract-amount">Compensation Amount</label>
              <input
                aria-label="Compensation Amount"
                className={INPUT_CLASS}
                id="contract-amount"
                onChange={e =>
                  onUpdateData<'contract'>(c => ({
                    ...c,
                    compensationAmount: Number(e.target.value) || 0
                  }))
                }
                type="number"
                value={contract.compensationAmount}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="contract-law">Governing Law</label>
              <input
                aria-label="Governing Law"
                className={INPUT_CLASS}
                id="contract-law"
                onChange={e => onUpdateData<'contract'>(c => ({ ...c, governingLaw: e.target.value }))}
                value={contract.governingLaw}
              />
            </div>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="contract-scope">Scope of Work</label>
            <textarea
              aria-label="Scope of Work"
              className={TEXTAREA_CLASS}
              id="contract-scope"
              onChange={e => onUpdateData<'contract'>(c => ({ ...c, scope: e.target.value }))}
              rows={2}
              value={contract.scope}
            />
          </div>
        </section>

        <section className={SECTION_CARD}>
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Contract Clauses</h3>
            <button
              className="inline-flex h-7 items-center gap-1 rounded-lg border border-border px-2.5 text-xs font-semibold hover:border-primary/40"
              onClick={() =>
                onUpdateData<'contract'>(c => ({
                  ...c,
                  clauses: [
                    ...c.clauses,
                    {
                      content: 'Clause terms [to confirm].',
                      id: `clause-${Date.now()}`,
                      requiresLegalReview: true,
                      title: `Article ${c.clauses.length + 1} — New Clause`
                    }
                  ]
                }))
              }
              type="button"
            >
              <Codicon name="add" size="0.75rem" />
              Add Clause
            </button>
          </div>
          <div className="space-y-3">
            {contract.clauses.map((clause, idx) => (
              <div className="rounded-lg border border-border/70 p-2.5 space-y-2" key={clause.id}>
                <div className="flex items-center justify-between gap-2">
                  <input
                    aria-label={`Clause Title ${idx + 1}`}
                    className={INPUT_CLASS}
                    onChange={e =>
                      onUpdateData<'contract'>(c => ({
                        ...c,
                        clauses: c.clauses.map(cl =>
                          cl.id === clause.id ? { ...cl, title: e.target.value } : cl
                        )
                      }))
                    }
                    value={clause.title}
                  />
                  <div className="flex shrink-0 items-center gap-2">
                    <label className="flex items-center gap-1 text-[0.6875rem] font-medium text-amber-600 dark:text-amber-400 cursor-pointer">
                      <input
                        checked={clause.requiresLegalReview}
                        onChange={e =>
                          onUpdateData<'contract'>(c => ({
                            ...c,
                            clauses: c.clauses.map(cl =>
                              cl.id === clause.id ? { ...cl, requiresLegalReview: e.target.checked } : cl
                            )
                          }))
                        }
                        type="checkbox"
                      />
                      Legal Review
                    </label>
                    {contract.clauses.length > 1 && (
                      <button
                        aria-label={`Remove Clause ${idx + 1}`}
                        className="rounded-lg p-1 text-muted-foreground transition hover:bg-muted hover:text-destructive"
                        onClick={() =>
                          onUpdateData<'contract'>(c => ({
                            ...c,
                            clauses: c.clauses.filter(cl => cl.id !== clause.id)
                          }))
                        }
                        type="button"
                      >
                        <Codicon name="trash" size="0.75rem" />
                      </button>
                    )}
                  </div>
                </div>
                <textarea
                  aria-label={`Clause Content ${idx + 1}`}
                  className={TEXTAREA_CLASS}
                  onChange={e =>
                    onUpdateData<'contract'>(c => ({
                      ...c,
                      clauses: c.clauses.map(cl =>
                        cl.id === clause.id ? { ...cl, content: e.target.value } : cl
                      )
                    }))
                  }
                  rows={2}
                  value={clause.content}
                />
              </div>
            ))}
          </div>
        </section>
      </div>
    )
  }

  if (doc.type === 'plan') {
    const plan = doc.data as BusinessPlanData
    const projections = calculateBusinessPlanProjections(plan.financialAssumptions)
    const fa = plan.financialAssumptions

    const updateAssumption = (key: keyof typeof fa, val: number) => {
      onUpdateData<'plan'>(c => ({
        ...c,
        financialAssumptions: {
          ...c.financialAssumptions,
          [key]: val
        }
      }))
    }

    return (
      <div className="space-y-4">
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Company Profile</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className={LABEL_CLASS} htmlFor="plan-company">Company Name</label>
              <input
                aria-label="Company Name"
                className={INPUT_CLASS}
                id="plan-company"
                onChange={e => onUpdateData<'plan'>(c => ({ ...c, companyName: e.target.value }))}
                value={plan.companyName}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="plan-industry">Industry</label>
              <input
                aria-label="Industry"
                className={INPUT_CLASS}
                id="plan-industry"
                onChange={e => onUpdateData<'plan'>(c => ({ ...c, industry: e.target.value }))}
                value={plan.industry}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="plan-currency">Currency</label>
              <select
                aria-label="Plan Currency"
                className={INPUT_CLASS}
                id="plan-currency"
                onChange={e => onUpdateData<'plan'>(c => ({ ...c, currency: e.target.value as CurrencyCode }))}
                value={plan.currency}
              >
                <option value="XAF">FCFA (XAF)</option>
                <option value="EUR">EUR (€)</option>
                <option value="USD">USD ($)</option>
              </select>
            </div>
          </div>
        </section>

        {/* Financial Assumptions */}
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
            3-Year Financial Model Assumptions (Deterministic)
          </h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <label className={LABEL_CLASS} htmlFor="fa-unit-price">Unit Price</label>
              <input
                aria-label="Unit Price"
                className={INPUT_CLASS}
                id="fa-unit-price"
                onChange={e => updateAssumption('unitPrice', Number(e.target.value) || 0)}
                type="number"
                value={fa.unitPrice}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="fa-unit-cost">Unit Variable Cost</label>
              <input
                aria-label="Unit Variable Cost"
                className={INPUT_CLASS}
                id="fa-unit-cost"
                onChange={e => updateAssumption('unitVariableCost', Number(e.target.value) || 0)}
                type="number"
                value={fa.unitVariableCost}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="fa-y1-units">Year 1 Units</label>
              <input
                aria-label="Year 1 Units"
                className={INPUT_CLASS}
                id="fa-y1-units"
                onChange={e => updateAssumption('year1Units', Number(e.target.value) || 0)}
                type="number"
                value={fa.year1Units}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="fa-fixed-costs">Monthly Fixed Costs</label>
              <input
                aria-label="Monthly Fixed Costs"
                className={INPUT_CLASS}
                id="fa-fixed-costs"
                onChange={e => updateAssumption('monthlyFixedCosts', Number(e.target.value) || 0)}
                type="number"
                value={fa.monthlyFixedCosts}
              />
            </div>
          </div>

          <div className="rounded-lg bg-muted/40 p-2.5 text-xs">
            <div className="font-semibold text-primary">
              Break-Even Threshold: {projections.breakEvenUnitsPerYear ?? 'N/A'} units/year · Year 1 Revenue:{' '}
              <span data-testid="plan-y1-revenue">
                {formatCurrency(projections.years[0]?.revenue ?? 0, plan.currency, doc.language)}
              </span>
            </div>
          </div>
        </section>

        {/* 14 Sections */}
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
            Business Plan Sections (14 Pillars)
          </h3>
          <div className="space-y-3">
            {PLAN_SECTION_LABELS.map(sec => (
              <div className="space-y-1" key={sec.key}>
                <div className="flex items-center justify-between">
                  <label className={LABEL_CLASS} htmlFor={`plan-sec-${sec.key}`}>
                    {doc.language === 'fr' ? sec.labelFr : sec.labelEn}
                  </label>
                  <button
                    className="inline-flex h-6 items-center gap-1 rounded bg-primary/10 px-2 text-[0.65rem] font-semibold text-primary disabled:opacity-50"
                    disabled={!canUseAi || aiBusy !== null}
                    onClick={() =>
                      onRunAi('expand_section', plan.sections[sec.key], sec.labelEn, output =>
                        onUpdateData<'plan'>(c => ({
                          ...c,
                          sections: { ...c.sections, [sec.key]: output }
                        }))
                      )
                    }
                    type="button"
                  >
                    <Codicon name="sparkle" size="0.65rem" />
                    AI Expand
                  </button>
                </div>
                <textarea
                  aria-label={sec.labelEn}
                  className={TEXTAREA_CLASS}
                  id={`plan-sec-${sec.key}`}
                  onChange={e =>
                    onUpdateData<'plan'>(c => ({
                      ...c,
                      sections: { ...c.sections, [sec.key]: e.target.value }
                    }))
                  }
                  rows={2}
                  value={plan.sections[sec.key]}
                />
              </div>
            ))}
          </div>
        </section>
      </div>
    )
  }

  if (doc.type === 'deck') {
    const deck = doc.data as PitchDeckData
    const safeIdx = Math.min(Math.max(0, activeSlideIndex), Math.max(0, deck.slides.length - 1))
    const slide = deck.slides[safeIdx]

    const updateSlide = (updater: (s: PitchSlide) => PitchSlide) => {
      onUpdateData<'deck'>(c => ({
        ...c,
        slides: c.slides.map((item, idx) => (idx === safeIdx ? updater(item) : item))
      }))
    }

    const moveSlide = (dir: -1 | 1) => {
      const target = safeIdx + dir

      if (target < 0 || target >= deck.slides.length) {
        return
      }

      onUpdateData<'deck'>(c => {
        const next = [...c.slides]
        const currentItem = next[safeIdx]
        const swapItem = next[target]

        if (currentItem && swapItem) {
          next[safeIdx] = swapItem
          next[target] = currentItem
        }

        return { ...c, slides: next }
      })
      onSelectSlide(target)
    }

    const addSlide = () => {
      const newIdx = deck.slides.length
      onUpdateData<'deck'>(c => ({
        ...c,
        slides: [
          ...c.slides,
          {
            bullets: ['Key takeaway #1 [to confirm]', 'Key takeaway #2 [to confirm]'],
            id: `slide-${Date.now()}`,
            key: 'custom',
            layout: 'split',
            metricLabel: 'Key Metric',
            metricValue: '[to confirm]',
            speakerNotes: '',
            subtitle: 'Supporting slide subtitle',
            title: `${c.slides.length + 1}. Custom Slide`
          }
        ]
      }))
      onSelectSlide(newIdx)
    }

    const deleteSlide = () => {
      if (deck.slides.length <= 1) {
        return
      }

      onUpdateData<'deck'>(c => ({
        ...c,
        slides: c.slides.filter((_, idx) => idx !== safeIdx)
      }))
      onSelectSlide(Math.max(0, safeIdx - 1))
    }

    return (
      <div className="space-y-4">
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">Pitch Deck Metadata</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLASS} htmlFor="deck-company">Company Name</label>
              <input
                aria-label="Deck Company Name"
                className={INPUT_CLASS}
                id="deck-company"
                onChange={e => onUpdateData<'deck'>(c => ({ ...c, companyName: e.target.value }))}
                value={deck.companyName}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="deck-tagline">Tagline</label>
              <input
                aria-label="Deck Tagline"
                className={INPUT_CLASS}
                id="deck-tagline"
                onChange={e => onUpdateData<'deck'>(c => ({ ...c, tagline: e.target.value }))}
                value={deck.tagline}
              />
            </div>
          </div>
        </section>

        {/* Slide Manager */}
        <section className={SECTION_CARD}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
              Slides ({safeIdx + 1} / {deck.slides.length})
            </h3>
            <div className="flex items-center gap-1.5">
              <button
                aria-label="Move Slide Up"
                className="inline-flex h-7 items-center rounded border border-border px-2 text-xs disabled:opacity-40"
                disabled={safeIdx === 0}
                onClick={() => moveSlide(-1)}
                type="button"
              >
                <Codicon name="arrow-up" size="0.75rem" />
              </button>
              <button
                aria-label="Move Slide Down"
                className="inline-flex h-7 items-center rounded border border-border px-2 text-xs disabled:opacity-40"
                disabled={safeIdx === deck.slides.length - 1}
                onClick={() => moveSlide(1)}
                type="button"
              >
                <Codicon name="arrow-down" size="0.75rem" />
              </button>
              <button
                className="inline-flex h-7 items-center gap-1 rounded border border-border px-2.5 text-xs font-semibold hover:border-primary/40"
                onClick={addSlide}
                type="button"
              >
                <Codicon name="add" size="0.75rem" />
                Add Slide
              </button>
              {deck.slides.length > 1 && (
                <button
                  aria-label="Delete Slide"
                  className="inline-flex h-7 items-center rounded border border-border px-2 text-xs text-muted-foreground hover:text-destructive"
                  onClick={deleteSlide}
                  type="button"
                >
                  <Codicon name="trash" size="0.75rem" />
                </button>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {deck.slides.map((s, idx) => (
              <button
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  idx === safeIdx
                    ? 'bg-primary text-primary-foreground'
                    : 'border border-border bg-background text-muted-foreground hover:text-foreground'
                }`}
                key={s.id}
                onClick={() => onSelectSlide(idx)}
                type="button"
              >
                {idx + 1}. {s.title.replace(/^\d+\.\s*/, '').slice(0, 16)}
              </button>
            ))}
          </div>

          {slide && (
            <div className="space-y-3 pt-2">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className={LABEL_CLASS} htmlFor="slide-title">Slide Title</label>
                  <input
                    aria-label="Slide Title"
                    className={INPUT_CLASS}
                    id="slide-title"
                    onChange={e => updateSlide(s => ({ ...s, title: e.target.value }))}
                    value={slide.title}
                  />
                </div>
                <div>
                  <label className={LABEL_CLASS} htmlFor="slide-subtitle">Slide Subtitle</label>
                  <input
                    aria-label="Slide Subtitle"
                    className={INPUT_CLASS}
                    id="slide-subtitle"
                    onChange={e => updateSlide(s => ({ ...s, subtitle: e.target.value }))}
                    value={slide.subtitle}
                  />
                </div>
                <div>
                  <label className={LABEL_CLASS} htmlFor="slide-metric-label">Key Metric Label</label>
                  <input
                    aria-label="Key Metric Label"
                    className={INPUT_CLASS}
                    id="slide-metric-label"
                    onChange={e => updateSlide(s => ({ ...s, metricLabel: e.target.value }))}
                    value={slide.metricLabel}
                  />
                </div>
                <div>
                  <label className={LABEL_CLASS} htmlFor="slide-metric-value">Key Metric Value</label>
                  <input
                    aria-label="Key Metric Value"
                    className={INPUT_CLASS}
                    id="slide-metric-value"
                    onChange={e => updateSlide(s => ({ ...s, metricValue: e.target.value }))}
                    value={slide.metricValue}
                  />
                </div>
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label className={LABEL_CLASS} htmlFor="slide-bullets">Slide Key Points (one per line)</label>
                  <button
                    className="inline-flex h-6 items-center gap-1 rounded bg-primary/10 px-2 text-[0.65rem] font-semibold text-primary disabled:opacity-50"
                    disabled={!canUseAi || aiBusy !== null}
                    onClick={() =>
                      onRunAi('refine_slide', slide.bullets.join('\n'), slide.title, output =>
                        updateSlide(s => ({
                          ...s,
                          bullets: output
                            .split(/\r?\n/)
                            .map(l => l.trim())
                            .filter(Boolean)
                        }))
                      )
                    }
                    type="button"
                  >
                    <Codicon name="sparkle" size="0.65rem" />
                    AI Refine Slide
                  </button>
                </div>
                <textarea
                  aria-label="Slide Bullets"
                  className={TEXTAREA_CLASS}
                  id="slide-bullets"
                  onChange={e =>
                    updateSlide(s => ({
                      ...s,
                      bullets: e.target.value.split(/\r?\n/)
                    }))
                  }
                  rows={4}
                  value={slide.bullets.join('\n')}
                />
              </div>

              <div>
                <label className={LABEL_CLASS} htmlFor="slide-notes">Speaker Notes</label>
                <textarea
                  aria-label="Speaker Notes"
                  className={TEXTAREA_CLASS}
                  id="slide-notes"
                  onChange={e => updateSlide(s => ({ ...s, speakerNotes: e.target.value }))}
                  rows={2}
                  value={slide.speakerNotes}
                />
              </div>
            </div>
          )}
        </section>
      </div>
    )
  }

  if (doc.type === 'letter') {
    const letter = doc.data as CoverLetterData
    const savedCvs = allDocs.filter(d => d.type === 'cv')

    const linkCv = (cvId: string) => {
      const found = savedCvs.find(d => d.id === cvId)

      if (!found) {
        onUpdateData<'letter'>(c => ({ ...c, linkedCvId: '' }))

        return
      }

      const cvData = found.data as CVData
      const topAchievements = cvData.experience.flatMap(e => e.achievements).slice(0, 3)
      onUpdateData<'letter'>(c => ({
        ...c,
        achievements: topAchievements.length > 0 ? topAchievements : c.achievements,
        linkedCvId: cvId,
        senderEmail: cvData.email || c.senderEmail,
        senderLocation: cvData.location || c.senderLocation,
        senderName: cvData.fullName || c.senderName,
        senderPhone: cvData.phone || c.senderPhone,
        senderTitle: cvData.headline || c.senderTitle
      }))
    }

    return (
      <div className="space-y-4">
        <section className={SECTION_CARD}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLASS} htmlFor="letter-tone">Tone</label>
              <select
                aria-label="Letter Tone"
                className={INPUT_CLASS}
                id="letter-tone"
                onChange={e =>
                  onUpdateData<'letter'>(c => ({ ...c, tone: e.target.value as CoverLetterTone }))
                }
                value={letter.tone}
              >
                <option value="professional">Professional</option>
                <option value="executive">Executive</option>
                <option value="persuasive">Persuasive</option>
                <option value="concise">Concise</option>
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="letter-cv-link">Link to Saved CV</label>
              <select
                aria-label="Link to Saved CV"
                className={INPUT_CLASS}
                id="letter-cv-link"
                onChange={e => linkCv(e.target.value)}
                value={letter.linkedCvId}
              >
                <option value="">— Select a saved CV —</option>
                {savedCvs.map(cvDoc => (
                  <option key={cvDoc.id} value={cvDoc.id}>
                    {cvDoc.title}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="letter-sender">Sender Name</label>
              <input
                aria-label="Sender Name"
                className={INPUT_CLASS}
                id="letter-sender"
                onChange={e => onUpdateData<'letter'>(c => ({ ...c, senderName: e.target.value }))}
                value={letter.senderName}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="letter-company">Target Company Name</label>
              <input
                aria-label="Target Company Name"
                className={INPUT_CLASS}
                id="letter-company"
                onChange={e => onUpdateData<'letter'>(c => ({ ...c, companyName: e.target.value }))}
                value={letter.companyName}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="letter-job">Target Job Title</label>
              <input
                aria-label="Target Job Title"
                className={INPUT_CLASS}
                id="letter-job"
                onChange={e => onUpdateData<'letter'>(c => ({ ...c, jobTitle: e.target.value }))}
                value={letter.jobTitle}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="letter-recipient">Recipient Name</label>
              <input
                aria-label="Recipient Name"
                className={INPUT_CLASS}
                id="letter-recipient"
                onChange={e => onUpdateData<'letter'>(c => ({ ...c, recipientName: e.target.value }))}
                value={letter.recipientName}
              />
            </div>
          </div>

          <div>
            <label className={LABEL_CLASS} htmlFor="letter-opening">Opening Paragraph</label>
            <textarea
              aria-label="Opening Paragraph"
              className={TEXTAREA_CLASS}
              id="letter-opening"
              onChange={e => onUpdateData<'letter'>(c => ({ ...c, opening: e.target.value }))}
              rows={2}
              value={letter.opening}
            />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className={LABEL_CLASS} htmlFor="letter-body">Body Paragraphs</label>
              <button
                className="inline-flex h-6 items-center gap-1 rounded bg-primary/10 px-2 text-[0.65rem] font-semibold text-primary disabled:opacity-50"
                disabled={!canUseAi || aiBusy !== null}
                onClick={() =>
                  onRunAi('polish_letter', letter.bodyParagraphs.join('\n\n'), letter.jobTitle, output =>
                    onUpdateData<'letter'>(c => ({
                      ...c,
                      bodyParagraphs: output.split(/\n\n+/).filter(Boolean)
                    }))
                  )
                }
                type="button"
              >
                <Codicon name="sparkle" size="0.65rem" />
                AI Polish Letter
              </button>
            </div>
            <textarea
              aria-label="Body Paragraphs"
              className={TEXTAREA_CLASS}
              id="letter-body"
              onChange={e =>
                onUpdateData<'letter'>(c => ({
                  ...c,
                  bodyParagraphs: e.target.value.split(/\n\n+/)
                }))
              }
              rows={4}
              value={letter.bodyParagraphs.join('\n\n')}
            />
          </div>
        </section>
      </div>
    )
  }

  if (doc.type === 'attestation') {
    const att = doc.data as AttestationData

    return (
      <div className="space-y-4">
        <section className={SECTION_CARD}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
            Certificate & Attestation Details
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLASS} htmlFor="att-category">Category</label>
              <select
                aria-label="Certificate Category"
                className={INPUT_CLASS}
                id="att-category"
                onChange={e =>
                  onUpdateData<'attestation'>(c => ({
                    ...c,
                    category: e.target.value as AttestationCategory
                  }))
                }
                value={att.category}
              >
                <option value="employment">Employment Certificate (Travail)</option>
                <option value="internship">Internship Certificate (Stage)</option>
                <option value="experience">Work Experience Attestation</option>
                <option value="training">Training Completion Certificate</option>
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="att-ref">Reference Number</label>
              <input
                aria-label="Reference Number"
                className={INPUT_CLASS}
                id="att-ref"
                onChange={e =>
                  onUpdateData<'attestation'>(c => ({ ...c, referenceNumber: e.target.value }))
                }
                value={att.referenceNumber}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="att-issuer">Issuer Company</label>
              <input
                aria-label="Issuer Company"
                className={INPUT_CLASS}
                id="att-issuer"
                onChange={e =>
                  onUpdateData<'attestation'>(c => ({ ...c, issuerCompany: e.target.value }))
                }
                value={att.issuerCompany}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="att-recipient">Recipient Full Name</label>
              <input
                aria-label="Recipient Full Name"
                className={INPUT_CLASS}
                id="att-recipient"
                onChange={e =>
                  onUpdateData<'attestation'>(c => ({ ...c, recipientFullName: e.target.value }))
                }
                value={att.recipientFullName}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="att-role">Role / Position</label>
              <input
                aria-label="Recipient Role"
                className={INPUT_CLASS}
                id="att-role"
                onChange={e =>
                  onUpdateData<'attestation'>(c => ({ ...c, recipientRole: e.target.value }))
                }
                value={att.recipientRole}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="att-signatory">Signatory Name</label>
              <input
                aria-label="Attestation Signatory Name"
                className={INPUT_CLASS}
                id="att-signatory"
                onChange={e =>
                  onUpdateData<'attestation'>(c => ({ ...c, signatoryName: e.target.value }))
                }
                value={att.signatoryName}
              />
            </div>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="att-body">Official Attestation Text</label>
            <textarea
              aria-label="Official Attestation Text"
              className={TEXTAREA_CLASS}
              id="att-body"
              onChange={e => onUpdateData<'attestation'>(c => ({ ...c, bodyText: e.target.value }))}
              rows={4}
              value={att.bodyText}
            />
          </div>
        </section>
      </div>
    )
  }

  // Scan Document Workspace
  const scan = doc.data as ScanDocumentData

  return (
    <div className="space-y-4">
      <section className={SECTION_CARD}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
              OCR Extracted Document
            </h3>
            <p className="text-[0.6875rem] text-muted-foreground">
              Source: {scan.sourceFileName} ({scan.sourceMimeType})
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-lg border border-border bg-background px-2.5 text-xs font-semibold hover:border-primary/40">
              <Codicon name="cloud-upload" size="0.75rem" />
              Scan Another File
              <input
                accept=".pdf,.jpg,.jpeg,.png"
                aria-label="Scan Another File"
                className="hidden"
                onChange={e => {
                  const f = e.target.files?.[0]

                  if (f) {
                    onReplaceScanFile(f)
                  }
                }}
                type="file"
              />
            </label>
            <button
              className="inline-flex h-7 items-center gap-1 rounded-lg bg-primary/10 px-2.5 text-xs font-semibold text-primary disabled:opacity-50"
              disabled={!canUseAi || aiBusy !== null}
              onClick={() =>
                onRunAi('summarize_scan', scan.editedText, scan.sourceFileName, output =>
                  onUpdateData<'scan'>(c => ({ ...c, structuredSummary: output }))
                )
              }
              type="button"
            >
              <Codicon name="sparkle" size="0.75rem" />
              AI Summarize Scan
            </button>
          </div>
        </div>

        <div>
          <label className={LABEL_CLASS} htmlFor="scan-summary">Structured Summary</label>
          <input
            aria-label="Structured Summary"
            className={INPUT_CLASS}
            id="scan-summary"
            onChange={e => onUpdateData<'scan'>(c => ({ ...c, structuredSummary: e.target.value }))}
            value={scan.structuredSummary}
          />
        </div>

        <div>
          <label className={LABEL_CLASS} htmlFor="scan-edited-text">
            Extracted Text (Editable — Unclear segments marked with [illegible])
          </label>
          <textarea
            aria-label="Extracted Text"
            className={TEXTAREA_CLASS}
            id="scan-edited-text"
            onChange={e => onUpdateData<'scan'>(c => ({ ...c, editedText: e.target.value }))}
            rows={12}
            value={scan.editedText}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
          <span className="text-[0.6875rem] font-semibold text-muted-foreground">
            Convert extracted scan into structured document:
          </span>
          <button
            className="inline-flex h-7 items-center gap-1 rounded-lg border border-border bg-background px-2.5 text-xs font-semibold hover:border-primary/40"
            onClick={() =>
              createBusinessDocument('cv', {
                initialData: { summary: scan.editedText },
                language: doc.language,
                title: `CV (${scan.sourceFileName})`
              })
            }
            type="button"
          >
            Convert to CV Draft
          </button>
          <button
            className="inline-flex h-7 items-center gap-1 rounded-lg border border-border bg-background px-2.5 text-xs font-semibold hover:border-primary/40"
            onClick={() =>
              createBusinessDocument('invoice', {
                initialData: { notes: scan.editedText },
                language: doc.language,
                title: `Facture (${scan.sourceFileName})`
              })
            }
            type="button"
          >
            Convert to Invoice Draft
          </button>
          <button
            className="inline-flex h-7 items-center gap-1 rounded-lg border border-border bg-background px-2.5 text-xs font-semibold hover:border-primary/40"
            onClick={() =>
              createBusinessDocument('contract', {
                initialData: { scope: scan.editedText },
                language: doc.language,
                title: `Contrat (${scan.sourceFileName})`
              })
            }
            type="button"
          >
            Convert to Contract Draft
          </button>
        </div>
      </section>
    </div>
  )
}
