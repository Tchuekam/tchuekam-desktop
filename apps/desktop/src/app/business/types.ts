import type { BuilderId } from './prompts'

export type DocumentType = BuilderId | 'scan'

export type DocumentLanguage = 'fr' | 'en'

export type CurrencyCode = 'XAF' | 'EUR' | 'USD'

export type ExportFormat = 'pdf' | 'docx' | 'xlsx' | 'pptx'

export type CVTemplateId =
  | 'modern'
  | 'executive'
  | 'minimalist'
  | 'corporate'
  | 'academic'
  | 'creative'
  | 'graduate'
  | 'technical'

export interface DocumentTemplate {
  accentColor: string
  description: string
  documentType: DocumentType
  fontFamily: 'sans' | 'serif' | 'mono'
  headerStyle: 'banner' | 'centered' | 'minimal' | 'sidebar'
  id: string
  name: string
}

export interface CVExperienceItem {
  achievements: string[]
  company: string
  current: boolean
  endDate: string
  id: string
  location: string
  role: string
  startDate: string
}

export interface CVEducationItem {
  degree: string
  endDate: string
  field: string
  honors: string
  id: string
  institution: string
  location: string
  startDate: string
}

export interface CVLanguageItem {
  id: string
  language: string
  level: 'Native' | 'Fluent' | 'Professional' | 'Intermediate' | 'Basic'
}

export interface CVCertificationItem {
  date: string
  id: string
  issuer: string
  name: string
}

export interface CVProjectItem {
  description: string
  id: string
  link: string
  name: string
  role: string
}

export interface CVCustomSection {
  content: string
  id: string
  title: string
}

export type CVSectionKey =
  | 'summary'
  | 'experience'
  | 'education'
  | 'skills'
  | 'languages'
  | 'certifications'
  | 'projects'
  | 'volunteer'
  | 'references'
  | 'custom'

export interface CVData {
  certifications: CVCertificationItem[]
  customSections: CVCustomSection[]
  education: CVEducationItem[]
  email: string
  experience: CVExperienceItem[]
  fullName: string
  headline: string
  languages: CVLanguageItem[]
  linkedin: string
  location: string
  phone: string
  projects: CVProjectItem[]
  references: string
  sectionOrder: CVSectionKey[]
  skills: string[]
  summary: string
  targetJobDescription: string
  volunteer: string
  website: string
}

export interface LineItem {
  description: string
  discountPercent: number
  id: string
  optional?: boolean
  quantity: number
  selected?: boolean
  taxRatePercent: number
  unitPrice: number
}

export type PaymentMethodType = 'momo' | 'orange_money' | 'bank_transfer' | 'cash' | 'other'

export type InvoicePaymentStatus = 'draft' | 'unpaid' | 'partially_paid' | 'paid' | 'overdue'

export interface InvoicePartySeller {
  address: string
  companyName: string
  email: string
  logoDataUrl: string
  niu: string
  phone: string
  rccm: string
}

export interface InvoicePartyClient {
  address: string
  companyName: string
  email: string
  name: string
  phone: string
}

export interface InvoiceData {
  amountPaid: number
  client: InvoicePartyClient
  currency: CurrencyCode
  description: string
  dueDate: string
  invoiceNumber: string
  issueDate: string
  items: LineItem[]
  notes: string
  paymentDetails: string
  paymentMethod: PaymentMethodType
  paymentStatus: InvoicePaymentStatus
  paymentTerms: string
  seller: InvoicePartySeller
  signatoryName: string
}

export type QuoteStatus = 'draft' | 'sent' | 'accepted' | 'declined'

export interface QuoteData {
  acceptanceNote: string
  client: InvoicePartyClient
  convertedInvoiceId?: string
  currency: CurrencyCode
  description: string
  issueDate: string
  items: LineItem[]
  notes: string
  paymentDetails: string
  paymentMethod: PaymentMethodType
  paymentTerms: string
  quoteNumber: string
  seller: InvoicePartySeller
  signatoryName: string
  status: QuoteStatus
  validUntil: string
}

export type ContractCategory =
  | 'service'
  | 'employment'
  | 'nda'
  | 'lease'
  | 'consulting'
  | 'partnership'

export interface ContractClause {
  content: string
  id: string
  requiresLegalReview: boolean
  title: string
}

export interface ContractData {
  category: ContractCategory
  clauses: ContractClause[]
  compensationAmount: number
  confidentiality: string
  currency: CurrencyCode
  disputeResolution: string
  duration: string
  effectiveDate: string
  governingLaw: string
  partyAAddress: string
  partyAName: string
  partyARegistration: string
  partyBAddress: string
  partyBName: string
  partyBRegistration: string
  paymentConditions: string
  responsibilities: string
  scope: string
  signatoryA: string
  signatoryB: string
  terminationConditions: string
}

export type BusinessPlanSectionKey =
  | 'executiveSummary'
  | 'companyOverview'
  | 'problem'
  | 'solution'
  | 'marketAnalysis'
  | 'competitiveAnalysis'
  | 'productsServices'
  | 'businessModel'
  | 'marketingStrategy'
  | 'operations'
  | 'managementTeam'
  | 'financialProjections'
  | 'fundingRequirements'
  | 'riskAnalysis'

export interface FinancialAssumptions {
  initialInvestment: number
  monthlyFixedCosts: number
  taxRatePercent: number
  unitPrice: number
  unitVariableCost: number
  year1Units: number
  year2GrowthPercent: number
  year3GrowthPercent: number
}

export interface BusinessPlanData {
  companyName: string
  currency: CurrencyCode
  financialAssumptions: FinancialAssumptions
  industry: string
  location: string
  sections: Record<BusinessPlanSectionKey, string>
}

export type PitchSlideKey =
  | 'problem'
  | 'solution'
  | 'product'
  | 'market'
  | 'business_model'
  | 'traction'
  | 'competition'
  | 'go_to_market'
  | 'financials'
  | 'team'
  | 'funding_ask'
  | 'custom'

export interface PitchSlide {
  bullets: string[]
  id: string
  key: PitchSlideKey
  layout: 'hero' | 'split' | 'metrics' | 'grid'
  metricLabel: string
  metricValue: string
  speakerNotes: string
  subtitle: string
  title: string
}

export interface PitchDeckData {
  companyName: string
  currency: CurrencyCode
  presenterName: string
  raiseAmount: number
  slides: PitchSlide[]
  tagline: string
}

export type CoverLetterTone = 'professional' | 'executive' | 'persuasive' | 'concise'

export interface CoverLetterData {
  achievements: string[]
  bodyParagraphs: string[]
  closing: string
  companyAddress: string
  companyName: string
  date: string
  jobTitle: string
  linkedCvId: string
  opening: string
  recipientName: string
  recipientTitle: string
  senderEmail: string
  senderLocation: string
  senderName: string
  senderPhone: string
  senderTitle: string
  tone: CoverLetterTone
}

export type AttestationCategory = 'employment' | 'internship' | 'experience' | 'training'

export interface AttestationData {
  bodyText: string
  category: AttestationCategory
  department: string
  endDate: string
  isCurrent: boolean
  issueCity: string
  issueDate: string
  issuerAddress: string
  issuerCompany: string
  issuerNiu: string
  issuerRccm: string
  recipientFullName: string
  recipientRole: string
  referenceNumber: string
  signatoryName: string
  signatoryTitle: string
  startDate: string
}

export interface ScanDocumentData {
  confidenceNote: string
  editedText: string
  extractedAt: number
  rawText: string
  sourceFileName: string
  sourceMimeType: string
  structuredSummary: string
}

export interface DocumentDataMap {
  attestation: AttestationData
  contract: ContractData
  cv: CVData
  deck: PitchDeckData
  invoice: InvoiceData
  letter: CoverLetterData
  plan: BusinessPlanData
  quote: QuoteData
  scan: ScanDocumentData
}

export interface BusinessDocument<T extends DocumentType = DocumentType> {
  createdAt: number
  data: DocumentDataMap[T]
  id: string
  language: DocumentLanguage
  status: 'draft' | 'final'
  templateId: string
  title: string
  type: T
  updatedAt: number
}

export interface BusinessProfile {
  address: string
  bankDetails: string
  city: string
  companyName: string
  country: string
  defaultCurrency: CurrencyCode
  defaultTaxRate: number
  email: string
  logoDataUrl: string
  momoAccountName: string
  momoMerchantCode: string
  niu: string
  orangeMoneyCode: string
  orangeMoneyName: string
  paymentMethods: PaymentMethodType[]
  rccm: string
  signatoryName: string
  signatoryTitle: string
  telephone: string
  website: string
}

export interface PersonalProfile {
  defaultLanguage: DocumentLanguage
  email: string
  fullName: string
  headline: string
  linkedin: string
  location: string
  phone: string
  skills: string[]
  summary: string
  website: string
}

