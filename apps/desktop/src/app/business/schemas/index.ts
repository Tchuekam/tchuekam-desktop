import type {
  AttestationData,
  BusinessDocument,
  BusinessPlanData,
  BusinessProfile,
  ContractData,
  CoverLetterData,
  CVData,
  CVTemplateId,
  DocumentLanguage,
  DocumentTemplate,
  DocumentType,
  ExportFormat,
  InvoiceData,
  PersonalProfile,
  PitchDeckData,
  QuoteData,
  ScanDocumentData
} from '../types'
import { generateDocumentNumber } from '../utils/calculations'

export const CV_TEMPLATES: Record<CVTemplateId, DocumentTemplate> = {
  modern: {
    accentColor: '#0053FD',
    description: 'Clean two-tone header with structured ATS-friendly hierarchy.',
    documentType: 'cv',
    fontFamily: 'sans',
    headerStyle: 'banner',
    id: 'modern',
    name: 'Modern Professional'
  },
  executive: {
    accentColor: '#1E293B',
    description: 'Authoritative serif typography for C-suite and board roles.',
    documentType: 'cv',
    fontFamily: 'serif',
    headerStyle: 'centered',
    id: 'executive',
    name: 'Executive'
  },
  minimalist: {
    accentColor: '#0F172A',
    description: 'High-contrast monochrome layout with generous whitespace.',
    documentType: 'cv',
    fontFamily: 'sans',
    headerStyle: 'minimal',
    id: 'minimalist',
    name: 'Minimalist'
  },
  corporate: {
    accentColor: '#1D4ED8',
    description: 'Traditional structured layout tailored for finance, banking, and consulting.',
    documentType: 'cv',
    fontFamily: 'serif',
    headerStyle: 'centered',
    id: 'corporate',
    name: 'Corporate'
  },
  academic: {
    accentColor: '#7C2D12',
    description: 'Publication-ready curriculum vitae emphasizing education and research.',
    documentType: 'cv',
    fontFamily: 'serif',
    headerStyle: 'minimal',
    id: 'academic',
    name: 'Academic'
  },
  creative: {
    accentColor: '#C98A2B',
    description: 'Warm gold-accented editorial layout for design and marketing leaders.',
    documentType: 'cv',
    fontFamily: 'sans',
    headerStyle: 'sidebar',
    id: 'creative',
    name: 'Creative'
  },
  graduate: {
    accentColor: '#047857',
    description: 'Education-first structure highlighting internships, coursework, and projects.',
    documentType: 'cv',
    fontFamily: 'sans',
    headerStyle: 'banner',
    id: 'graduate',
    name: 'Graduate / Student'
  },
  technical: {
    accentColor: '#0369A1',
    description: 'Engineering-focused layout prioritizing skills, systems, and impact metrics.',
    documentType: 'cv',
    fontFamily: 'mono',
    headerStyle: 'minimal',
    id: 'technical',
    name: 'Technical'
  }
}

export const ALL_TEMPLATES: DocumentTemplate[] = [
  ...Object.values(CV_TEMPLATES),
  {
    accentColor: '#C98A2B',
    description: 'Commercial invoice with OHADA / Cameroon NIU & RCCM header and MoMo/Orange Money footer.',
    documentType: 'invoice',
    fontFamily: 'sans',
    headerStyle: 'banner',
    id: 'invoice-ohada',
    name: 'Facture Commerciale OHADA'
  },
  {
    accentColor: '#0053FD',
    description: 'International service invoice in EUR/USD/FCFA with bank & mobile payment block.',
    documentType: 'invoice',
    fontFamily: 'sans',
    headerStyle: 'minimal',
    id: 'invoice-modern',
    name: 'Modern International Invoice'
  },
  {
    accentColor: '#C98A2B',
    description: 'Itemized commercial quotation with optional items and client acceptance signature block.',
    documentType: 'quote',
    fontFamily: 'sans',
    headerStyle: 'banner',
    id: 'quote-standard',
    name: 'Devis Proforma Standard'
  },
  {
    accentColor: '#1E293B',
    description: 'Numbered bilateral agreement with legal review callouts and dual signature block.',
    documentType: 'contract',
    fontFamily: 'serif',
    headerStyle: 'centered',
    id: 'contract-standard',
    name: 'Contrat Prestation / NDA'
  },
  {
    accentColor: '#0053FD',
    description: '14-section investor business plan with deterministic 3-year financial projection tables.',
    documentType: 'plan',
    fontFamily: 'sans',
    headerStyle: 'banner',
    id: 'plan-investor',
    name: 'Investor Business Plan'
  },
  {
    accentColor: '#0038A8',
    description: '11-slide widescreen 16:9 venture pitch deck ready for PPTX and PDF export.',
    documentType: 'deck',
    fontFamily: 'sans',
    headerStyle: 'banner',
    id: 'deck-venture',
    name: 'Venture Pitch Deck (16:9)'
  },
  {
    accentColor: '#0F172A',
    description: 'Bilingual FR/EN formal cover letter linked to your candidate profile.',
    documentType: 'letter',
    fontFamily: 'serif',
    headerStyle: 'minimal',
    id: 'letter-formal',
    name: 'Formal Cover Letter'
  },
  {
    accentColor: '#17694D',
    description: 'Official employer or internship certificate with company header and stamp/signature block.',
    documentType: 'attestation',
    fontFamily: 'serif',
    headerStyle: 'centered',
    id: 'attestation-official',
    name: 'Attestation Officielle'
  },
  {
    accentColor: '#0A2F6B',
    description: 'Extracted OCR text workspace preserving layout and marking unclear segments.',
    documentType: 'scan',
    fontFamily: 'sans',
    headerStyle: 'minimal',
    id: 'scan-default',
    name: 'Scan Document Workspace'
  }
]

export const SUPPORTED_EXPORT_FORMATS: Record<DocumentType, ExportFormat[]> = {
  attestation: ['pdf', 'docx'],
  contract: ['pdf', 'docx'],
  cv: ['pdf', 'docx'],
  deck: ['pptx', 'pdf', 'docx'],
  invoice: ['pdf', 'docx', 'xlsx'],
  letter: ['pdf', 'docx'],
  plan: ['pdf', 'docx', 'xlsx'],
  quote: ['pdf', 'docx', 'xlsx'],
  scan: ['pdf', 'docx']
}

export const DEFAULT_BUSINESS_PROFILE: BusinessProfile = {
  address: 'Rue Joss, Bonanjo',
  bankDetails: '',
  city: 'Douala',
  companyName: '',
  country: 'Cameroun',
  defaultCurrency: 'XAF',
  defaultTaxRate: 19.25,
  email: '',
  logoDataUrl: '',
  momoAccountName: '',
  momoMerchantCode: '',
  niu: '',
  orangeMoneyCode: '',
  orangeMoneyName: '',
  paymentMethods: ['momo', 'orange_money', 'bank_transfer'],
  rccm: '',
  signatoryName: '',
  signatoryTitle: 'Directeur Général',
  telephone: '',
  website: ''
}

export const DEFAULT_PERSONAL_PROFILE: PersonalProfile = {
  defaultLanguage: 'fr',
  email: '',
  fullName: '',
  headline: '',
  linkedin: '',
  location: 'Douala, Cameroun',
  phone: '',
  skills: [],
  summary: '',
  website: ''
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function futureIso(days: number): string {
  const dt = new Date(Date.now() + days * 86_400_000)

  return dt.toISOString().slice(0, 10)
}

export function createDefaultCVData(
  personal: PersonalProfile,
  language: DocumentLanguage
): CVData {
  const isFr = language === 'fr'

  return {
    certifications: [],
    customSections: [],
    education: [
      {
        degree: isFr ? 'Master / Diplôme d’Ingénieur [to confirm]' : 'B.Sc. / Master’s Degree [to confirm]',
        endDate: '2024',
        field: isFr ? 'Informatique & Gestion' : 'Computer Science & Management',
        honors: '',
        id: 'edu-1',
        institution: isFr ? 'Université [to confirm]' : 'University [to confirm]',
        location: personal.location || 'Douala',
        startDate: '2020'
      }
    ],
    email: personal.email || 'contact@example.com',
    experience: [
      {
        achievements: isFr
          ? [
              'Pilotage des opérations et amélioration de la productivité de +25% sur 12 mois.',
              'Coordination d’une équipe pluridisciplinaire de 6 collaborateurs.'
            ]
          : [
              'Led operational delivery and increased workflow efficiency by +25% over 12 months.',
              'Coordinated a cross-functional team of 6 specialists across key client accounts.'
            ],
        company: isFr ? 'Entreprise [to confirm]' : 'Company [to confirm]',
        current: true,
        endDate: isFr ? 'Présent' : 'Present',
        id: 'exp-1',
        location: personal.location || 'Douala',
        role: personal.headline || (isFr ? 'Responsable de Projet' : 'Project Lead'),
        startDate: '2024-01'
      }
    ],
    fullName: personal.fullName || (isFr ? 'Nom Prénom [to confirm]' : 'Full Name [to confirm]'),
    headline:
      personal.headline ||
      (isFr ? 'Spécialiste Opérations & Transformation Digitale' : 'Operations & Digital Transformation Specialist'),
    languages: [
      { id: 'lang-1', language: 'Français', level: 'Native' },
      { id: 'lang-2', language: 'English', level: 'Professional' }
    ],
    linkedin: personal.linkedin || '',
    location: personal.location || 'Douala, Cameroun',
    phone: personal.phone || '+237 600 00 00 00',
    projects: [],
    references: isFr ? 'Disponibles sur demande.' : 'Available upon request.',
    sectionOrder: [
      'summary',
      'experience',
      'education',
      'skills',
      'languages',
      'certifications',
      'projects',
      'volunteer',
      'references',
      'custom'
    ],
    skills:
      personal.skills.length > 0
        ? [...personal.skills]
        : isFr
          ? ['Gestion de projet', 'Analyse financière', 'Leadership', 'Stratégie digitale', 'Relation client']
          : ['Project Management', 'Financial Analysis', 'Team Leadership', 'Digital Strategy', 'Stakeholder Management'],
    summary:
      personal.summary ||
      (isFr
        ? 'Professionnel expérimenté spécialisé dans le pilotage de projets à fort impact, l’optimisation des processus métiers et la croissance opérationnelle.'
        : 'Results-driven professional experienced in leading high-impact projects, optimizing business operations, and driving measurable growth.'),
    targetJobDescription: '',
    volunteer: '',
    website: personal.website || ''
  }
}

export function createDefaultInvoiceData(
  profile: BusinessProfile,
  language: DocumentLanguage,
  existingCount = 0
): InvoiceData {
  const isFr = language === 'fr'
  const paymentLines: string[] = []

  if (profile.momoMerchantCode) {
    paymentLines.push(`MTN MoMo: ${profile.momoMerchantCode} (${profile.momoAccountName || profile.companyName})`)
  }

  if (profile.orangeMoneyCode) {
    paymentLines.push(`Orange Money: ${profile.orangeMoneyCode} (${profile.orangeMoneyName || profile.companyName})`)
  }

  if (profile.bankDetails) {
    paymentLines.push(`Banque: ${profile.bankDetails}`)
  }

  return {
    amountPaid: 0,
    client: {
      address: isFr ? 'Adresse du client [to confirm]' : 'Client address [to confirm]',
      companyName: isFr ? 'Société Cliente [to confirm]' : 'Client Company [to confirm]',
      email: '',
      name: isFr ? 'Contact Client [to confirm]' : 'Client Contact [to confirm]',
      phone: ''
    },
    currency: profile.defaultCurrency || 'XAF',
    description: isFr ? 'Prestations de services professionnels' : 'Professional services invoice',
    dueDate: futureIso(14),
    invoiceNumber: generateDocumentNumber('INV', existingCount),
    issueDate: todayIso(),
    items: [
      {
        description: isFr ? 'Consultation & accompagnement stratégique' : 'Strategic consulting & implementation',
        discountPercent: 0,
        id: 'item-1',
        quantity: 1,
        taxRatePercent: profile.defaultTaxRate ?? 19.25,
        unitPrice: profile.defaultCurrency === 'XAF' ? 250_000 : 500
      }
    ],
    notes: isFr
      ? 'Merci pour votre confiance. Veuillez mentionner le numéro de facture lors du règlement.'
      : 'Thank you for your business. Please reference the invoice number upon payment.',
    paymentDetails:
      paymentLines.join(' · ') ||
      (isFr
        ? 'MTN Mobile Money / Orange Money / Virement bancaire [to confirm]'
        : 'Mobile Money / Bank Transfer [to confirm]'),
    paymentMethod: profile.paymentMethods[0] || 'momo',
    paymentStatus: 'unpaid',
    paymentTerms: isFr ? 'Paiement à 14 jours date de facture' : 'Net 14 days from issue date',
    seller: {
      address: [profile.address, profile.city, profile.country].filter(Boolean).join(', '),
      companyName: profile.companyName || (isFr ? 'Votre Entreprise [to confirm]' : 'Your Company [to confirm]'),
      email: profile.email || '',
      logoDataUrl: profile.logoDataUrl || '',
      niu: profile.niu || '',
      phone: profile.telephone || '',
      rccm: profile.rccm || ''
    },
    signatoryName: profile.signatoryName || ''
  }
}

export function createDefaultQuoteData(
  profile: BusinessProfile,
  language: DocumentLanguage,
  existingCount = 0
): QuoteData {
  const base = createDefaultInvoiceData(profile, language, existingCount)
  const isFr = language === 'fr'

  return {
    acceptanceNote: isFr
      ? 'Bon pour accord — Signature et cachet du client précédés de la mention « Lu et approuvé »'
      : 'Accepted and agreed — Client signature and date',
    client: base.client,
    currency: base.currency,
    description: isFr ? 'Proposition commerciale et financière' : 'Commercial quotation & proposal',
    issueDate: base.issueDate,
    items: [
      ...base.items,
      {
        description: isFr ? 'Option : Support prioritaire et maintenance mensuelle' : 'Optional: Priority monthly support & maintenance',
        discountPercent: 0,
        id: 'item-opt-1',
        optional: true,
        quantity: 1,
        selected: true,
        taxRatePercent: profile.defaultTaxRate ?? 19.25,
        unitPrice: profile.defaultCurrency === 'XAF' ? 75_000 : 150
      }
    ],
    notes: isFr ? 'Ce devis est valable 30 jours à compter de sa date d’émission.' : 'This quotation is valid for 30 days from the date of issue.',
    paymentDetails: base.paymentDetails,
    paymentMethod: base.paymentMethod,
    paymentTerms: isFr ? '50% à la commande, 50% à la livraison' : '50% upon acceptance, 50% upon delivery',
    quoteNumber: generateDocumentNumber('DEV', existingCount),
    seller: base.seller,
    signatoryName: base.signatoryName,
    status: 'draft',
    validUntil: futureIso(30)
  }
}

export function createDefaultContractData(
  profile: BusinessProfile,
  language: DocumentLanguage
): ContractData {
  const isFr = language === 'fr'

  return {
    category: 'service',
    clauses: [
      {
        content: isFr
          ? 'Le Prestataire s’engage à exécuter les prestations décrites à l’Article 1 avec diligence et conformément aux règles de l’art.'
          : 'The Provider agrees to perform the services described in Section 1 with professional diligence and industry standards.',
        id: 'clause-1',
        requiresLegalReview: false,
        title: isFr ? 'Article 1 — Obligations des parties' : 'Section 1 — Obligations of the Parties'
      },
      {
        content: isFr
          ? 'La responsabilité totale de chaque partie au titre du présent contrat est plafonnée au montant total effectivement perçu [to confirm].'
          : 'Each party’s aggregate liability under this agreement shall not exceed the total fees paid hereunder [to confirm].',
        id: 'clause-2',
        requiresLegalReview: true,
        title: isFr ? 'Article 2 — Limitation de responsabilité' : 'Section 2 — Limitation of Liability'
      },
      {
        content: isFr
          ? 'Les droits de propriété intellectuelle sur les livrables sont transférés au Client après paiement intégral du prix convenu.'
          : 'Intellectual property rights in deliverables shall transfer to the Client upon full and final payment of all fees.',
        id: 'clause-3',
        requiresLegalReview: true,
        title: isFr ? 'Article 3 — Propriété intellectuelle' : 'Section 3 — Intellectual Property'
      }
    ],
    compensationAmount: profile.defaultCurrency === 'XAF' ? 500_000 : 1_000,
    confidentiality: isFr
      ? 'Chaque partie s’engage à conserver strictement confidentielles toutes les informations techniques, commerciales et financières échangées.'
      : 'Each party shall keep strictly confidential all technical, commercial, and financial information disclosed during the engagement.',
    currency: profile.defaultCurrency || 'XAF',
    disputeResolution: isFr
      ? 'Règlement amiable prioritaire sous 30 jours, à défaut compétence exclusive des juridictions de Douala [to confirm].'
      : 'Good-faith mediation within 30 days, failing which exclusive jurisdiction of the courts of [to confirm].',
    duration: isFr ? '6 mois renouvelables' : '6 months, renewable',
    effectiveDate: todayIso(),
    governingLaw: isFr ? 'Droit camerounais et Actes Uniformes OHADA [to confirm]' : 'Applicable law of [to confirm]',
    partyAAddress: [profile.address, profile.city, profile.country].filter(Boolean).join(', ') || '[to confirm]',
    partyAName: profile.companyName || (isFr ? 'Partie A (Prestataire) [to confirm]' : 'Party A (Provider) [to confirm]'),
    partyARegistration: [profile.rccm, profile.niu].filter(Boolean).join(' / ') || '[to confirm]',
    partyBAddress: isFr ? 'Adresse du Client [to confirm]' : 'Client Address [to confirm]',
    partyBName: isFr ? 'Partie B (Client) [to confirm]' : 'Party B (Client) [to confirm]',
    partyBRegistration: '[to confirm]',
    paymentConditions: isFr
      ? '50% à la signature, 50% à la réception définitive des livrables par Mobile Money ou virement.'
      : '50% upon signing, 50% upon final acceptance of deliverables.',
    responsibilities: isFr
      ? 'Fourniture des livrables dans les délais convenus ; collaboration active et validation par le Client.'
      : 'Timely delivery of milestones by Provider; timely review and access provisioning by Client.',
    scope: isFr
      ? 'Conception, développement et déploiement de solutions digitales [to confirm].'
      : 'Design, development, and deployment of digital business solutions [to confirm].',
    signatoryA: profile.signatoryName || '[to confirm]',
    signatoryB: '[to confirm]',
    terminationConditions: isFr
      ? 'Résiliation possible par chacune des parties moyennant un préavis écrit de 30 jours.'
      : 'Either party may terminate this agreement with 30 days written notice.'
  }
}

export function createDefaultBusinessPlanData(
  profile: BusinessProfile,
  language: DocumentLanguage
): BusinessPlanData {
  const isFr = language === 'fr'
  const isXaf = (profile.defaultCurrency || 'XAF') === 'XAF'

  return {
    companyName: profile.companyName || (isFr ? 'Nouvelle Entreprise [to confirm]' : 'New Venture [to confirm]'),
    currency: profile.defaultCurrency || 'XAF',
    financialAssumptions: {
      initialInvestment: isXaf ? 5_000_000 : 10_000,
      monthlyFixedCosts: isXaf ? 450_000 : 900,
      taxRatePercent: 25,
      unitPrice: isXaf ? 25_000 : 50,
      unitVariableCost: isXaf ? 9_000 : 18,
      year1Units: 420,
      year2GrowthPercent: 45,
      year3GrowthPercent: 50
    },
    industry: isFr ? 'Services Numériques & Technologie' : 'Technology & Business Services',
    location: [profile.city, profile.country].filter(Boolean).join(', ') || 'Douala, Cameroun',
    sections: {
      businessModel: isFr
        ? 'Modèle hybride combinant abonnements récurrents B2B et prestations d’intégration à forte marge.'
        : 'Hybrid B2B recurring subscription and high-margin implementation services model.',
      companyOverview: isFr
        ? 'Société basée à Douala proposant des solutions d’automatisation et de productivité pour les PME et grandes entreprises.'
        : 'Growth-stage company delivering automation and productivity infrastructure for SMEs and enterprises.',
      competitiveAnalysis: isFr
        ? 'Avantage compétitif fondé sur l’intégration locale (FCFA, Mobile Money, bilinguisme FR/EN) et la rapidité de déploiement.'
        : 'Differentiated by local payment integration (FCFA, Mobile Money), bilingual FR/EN support, and rapid deployment.',
      executiveSummary: isFr
        ? 'Synthèse exécutive : Notre entreprise répond à la demande croissante de digitalisation des opérations commerciales et financières en Afrique centrale.'
        : 'Executive Summary: Our venture addresses the growing demand for streamlined commercial and financial operations.',
      financialProjections: isFr
        ? 'Les projections financières sur 3 ans sont calculées de manière déterministe à partir des hypothèses explicites ci-contre (estimations illustratives).'
        : 'The 3-year financial projections are deterministically calculated from the explicit unit economics assumptions (illustrative estimates).',
      fundingRequirements: isFr
        ? 'Besoin de financement initial destiné au développement produit (45%), à l’acquisition commerciale (35%) et au fonds de roulement (20%).'
        : 'Initial capital allocation: Product engineering (45%), commercial go-to-market (35%), and working capital reserve (20%).',
      managementTeam: isFr
        ? 'Équipe dirigeante complémentaire réunissant expertise technique, gestion financière et développement commercial [to confirm].'
        : 'Complementary leadership team combining technical architecture, financial management, and commercial execution [to confirm].',
      marketAnalysis: isFr
        ? 'Marché en forte croissance porté par l’adoption du paiement mobile et la formalisation numérique des PME.'
        : 'Expanding addressable market driven by mobile money adoption and SME digital formalization.',
      marketingStrategy: isFr
        ? 'Acquisition directe B2B, partenariats sectoriels, démonstrations ciblées et recommandation client.'
        : 'Direct B2B sales, channel partnerships, targeted product demonstrations, and customer referrals.',
      operations: isFr
        ? 'Opérations basées à Douala avec infrastructure cloud sécurisée et support client réactif.'
        : 'Lean operational footprint backed by resilient cloud infrastructure and dedicated customer success.',
      problem: isFr
        ? 'Les PME perdent un temps considérable avec des outils fragmentés non adaptés aux réalités fiscales et monétaires locales.'
        : 'SMEs lose significant productivity using fragmented tools that lack local currency and compliance workflows.',
      productsServices: isFr
        ? 'Plateforme tout-en-un de gestion documentaire, facturation FCFA/MoMo et assistance IA.'
        : 'All-in-one workspace for business documents, invoicing, and AI-assisted operations.',
      riskAnalysis: isFr
        ? 'Risques identifiés : délais d’adoption commerciale, connectivité et évolution réglementaire — mitigés par une architecture locale/hors-ligne.'
        : 'Key risks: enterprise sales cycle length and connectivity variability — mitigated via offline-first desktop architecture.',
      solution: isFr
        ? 'Une suite intégrée permettant de créer, valider et exporter tous les documents critiques en quelques minutes.'
        : 'An integrated desktop suite enabling teams to draft, validate, and export critical business documents in minutes.'
    }
  }
}

export function createDefaultPitchDeckData(
  profile: BusinessProfile,
  language: DocumentLanguage
): PitchDeckData {
  const isFr = language === 'fr'
  const company = profile.companyName || 'TchueKAM Venture [to confirm]'
  const currency = profile.defaultCurrency || 'XAF'
  const raiseAmount = currency === 'XAF' ? 50_000_000 : 100_000

  return {
    companyName: company,
    currency,
    presenterName: profile.signatoryName || (isFr ? 'Fondateur / CEO [to confirm]' : 'Founder / CEO [to confirm]'),
    raiseAmount,
    slides: [
      {
        bullets: isFr
          ? ['Outils bureautiques fragmentés et coûteux', 'Absence d’intégration native FCFA / Mobile Money / OHADA', 'Perte de productivité sur les tâches administratives']
          : ['Fragmented and expensive legacy office tools', 'Lack of native FCFA, Mobile Money, and regional compliance workflows', 'High administrative overhead for growing SMEs'],
        id: 'slide-1',
        key: 'problem',
        layout: 'split',
        metricLabel: isFr ? 'Heures perdues / semaine' : 'Hours lost / week',
        metricValue: '12h+',
        speakerNotes: isFr ? 'Présenter la douleur concrète vécue par les dirigeants de PME.' : 'Highlight the concrete operational pain faced by SMEs.',
        subtitle: isFr ? 'Pourquoi le statu quo freine la croissance des entreprises' : 'Why legacy workflows hold back emerging businesses',
        title: isFr ? '1. Le Problème' : '1. The Problem'
      },
      {
        bullets: isFr
          ? ['Espace de travail unifié assisté par IA', 'Génération, édition et export instantanés (PDF, DOCX, XLSX, PPTX)', 'Conçu pour le contexte économique local et international']
          : ['Unified AI-powered business workspace', 'Instant creation, visual editing, and multi-format export', 'Built for both local FCFA/MoMo and international standards'],
        id: 'slide-2',
        key: 'solution',
        layout: 'hero',
        metricLabel: isFr ? 'Gain de rapidité' : 'Speed improvement',
        metricValue: '10x',
        speakerNotes: '',
        subtitle: isFr ? 'Une plateforme unique pour créer, valider et exporter' : 'One workspace to create, validate, and export',
        title: isFr ? '2. La Solution' : '2. The Solution'
      },
      {
        bullets: isFr
          ? ['Éditeur temps réel avec aperçu A4 & 16:9', 'Calculs financiers déterministes sans erreur d’arrondi', 'OCR direct des photos et PDF vers documents éditables']
          : ['Real-time split-screen editor with live A4 & 16:9 preview', 'Deterministic financial calculations with zero rounding drift', 'Direct photo & PDF OCR into editable documents'],
        id: 'slide-3',
        key: 'product',
        layout: 'grid',
        metricLabel: isFr ? 'Formats supportés' : 'Export formats',
        metricValue: 'PDF · DOCX · XLSX · PPTX',
        speakerNotes: '',
        subtitle: isFr ? 'Architecture produit de classe entreprise' : 'Enterprise-grade product architecture',
        title: isFr ? '3. Le Produit' : '3. Product Overview'
      },
      {
        bullets: isFr
          ? ['Croissance rapide de la formalisation numérique des PME en CEMAC & Afrique de l’Ouest', 'Forte pénétration du Mobile Money B2B', 'Marché adressable en expansion continue [to confirm]']
          : ['Rapid digital formalization of SMEs across Central & West Africa', 'High B2B Mobile Money adoption', 'Expanding total addressable market [to confirm]'],
        id: 'slide-4',
        key: 'market',
        layout: 'metrics',
        metricLabel: 'TAM / SAM [to confirm]',
        metricValue: '[to confirm]',
        speakerNotes: '',
        subtitle: isFr ? 'Opportunité de marché' : 'Market Opportunity',
        title: isFr ? '4. Le Marché' : '4. Market Size'
      },
      {
        bullets: isFr
          ? ['Abonnement Pro mensuel / annuel par utilisateur', 'Offre Entreprise avec profils multi-équipes et déploiement dédié', 'Marge brute logicielle élevée (>75% illustratif)']
          : ['Monthly / annual Pro SaaS subscription per seat', 'Enterprise tier with custom branding and multi-profile deployment', 'High software gross margin (>75% illustrative)'],
        id: 'slide-5',
        key: 'business_model',
        layout: 'split',
        metricLabel: isFr ? 'Marge brute cible' : 'Target Gross Margin',
        metricValue: '78%',
        speakerNotes: '',
        subtitle: isFr ? 'Revenus récurrents et prévisibles' : 'Predictable recurring revenue engine',
        title: isFr ? '5. Modèle Économique' : '5. Business Model'
      },
      {
        bullets: isFr
          ? ['Produit fonctionnel de bout en bout (Voix + Business Hub + Studio)', 'Premiers utilisateurs pilotes actifs [to confirm]', 'Pipeline commercial B2B engagé [to confirm]']
          : ['End-to-end production desktop platform live', 'Active pilot users and early enterprise interest [to confirm]', 'Growing B2B commercial pipeline [to confirm]'],
        id: 'slide-6',
        key: 'traction',
        layout: 'metrics',
        metricLabel: isFr ? 'Statut produit' : 'Product Readiness',
        metricValue: 'Production v2.0',
        speakerNotes: '',
        subtitle: isFr ? 'Jalons atteints et validation terrain' : 'Milestones achieved & validation',
        title: isFr ? '6. Traction' : '6. Traction & Milestones'
      },
      {
        bullets: isFr
          ? ['Canva / Resume.io : génériques, sans logique financière ou fiscale locale', 'Chatbots IA classiques : pas d’éditeur structuré ni d’export natif fiable', 'TchueKAM : IA agentique + éditeur structuré + conformité locale']
          : ['Canva / Resume.io: generic templates without local billing or agentic workflows', 'Standard AI chatbots: raw text prompts without structured editing or deterministic math', 'TchueKAM: Agentic AI + structured workspace + local FCFA/MoMo readiness'],
        id: 'slide-7',
        key: 'competition',
        layout: 'grid',
        metricLabel: isFr ? 'Différenciation' : 'Core Moat',
        metricValue: 'AI + Local Native',
        speakerNotes: '',
        subtitle: isFr ? 'Positionnement concurrentiel' : 'Competitive Landscape',
        title: isFr ? '7. Concurrence' : '7. Competition'
      },
      {
        bullets: isFr
          ? ['Vente directe aux cabinets, PME, incubateurs et écoles supérieures', 'Partenariats avec opérateurs fintech et chambres de commerce', 'Croissance organique via documents exportés et partagés']
          : ['Direct B2B outreach to SMEs, consultancies, incubators, and universities', 'Strategic partnerships with fintech ecosystems and business associations', 'Product-led growth via shared invoices, quotes, and CVs'],
        id: 'slide-8',
        key: 'go_to_market',
        layout: 'split',
        metricLabel: isFr ? 'Canaux prioritaires' : 'Primary Channels',
        metricValue: 'B2B + PLG',
        speakerNotes: '',
        subtitle: isFr ? 'Stratégie d’acquisition et de distribution' : 'Distribution & Growth Strategy',
        title: isFr ? '8. Go-to-Market' : '8. Go-to-Market'
      },
      {
        bullets: isFr
          ? ['Trajectoire de croissance sur 36 mois fondée sur des coûts maîtrisés', 'Atteinte du seuil de rentabilité dès la première phase d’expansion', 'Hypothèses détaillées disponibles dans le Business Plan']
          : ['36-month growth trajectory built on disciplined unit economics', 'Clear path to break-even profitability', 'Full sensitivity table linked in the Business Plan model'],
        id: 'slide-9',
        key: 'financials',
        layout: 'metrics',
        metricLabel: isFr ? 'Horizon' : 'Projection Horizon',
        metricValue: '3 Ans / Years',
        speakerNotes: '',
        subtitle: isFr ? 'Projections financières illustratives' : 'Illustrative Financial Projections',
        title: isFr ? '9. Projections Financières' : '9. Financials'
      },
      {
        bullets: isFr
          ? ['Direction technique & IA : architecture distribuée et applications desktop', 'Direction commerciale & opérations : connaissance approfondie du marché', 'Conseillers sectoriels [to confirm]']
          : ['Engineering & AI leadership: full-stack desktop and agentic systems', 'Commercial & Operations leadership: deep regional market execution', 'Domain advisors [to confirm]'],
        id: 'slide-10',
        key: 'team',
        layout: 'grid',
        metricLabel: isFr ? 'Équipe clé' : 'Core Team',
        metricValue: 'Founders [to confirm]',
        speakerNotes: '',
        subtitle: isFr ? 'L’équipe pour exécuter la vision' : 'The team built to execute this vision',
        title: isFr ? '10. L’Équipe' : '10. The Team'
      },
      {
        bullets: isFr
          ? ['45% Accélération R&D et infrastructure IA', '35% Déploiement commercial et partenariats B2B', '20% Opérations et trésorerie de sécurité (18 mois de runway)']
          : ['45% Product R&D and AI infrastructure scaling', '35% Commercial expansion and B2B partnerships', '20% Operations and working capital reserve (18-month runway)'],
        id: 'slide-11',
        key: 'funding_ask',
        layout: 'hero',
        metricLabel: isFr ? 'Montant recherché' : 'Target Raise',
        metricValue: currency === 'XAF' ? '50 000 000 FCFA' : '$100,000',
        speakerNotes: '',
        subtitle: isFr ? 'Utilisation des fonds et prochains jalons' : 'Use of proceeds & 18-month milestones',
        title: isFr ? '11. Levée de Fonds (Ask)' : '11. Funding Ask'
      }
    ],
    tagline: isFr
      ? 'Le système d’exploitation IA pour la productivité des entreprises'
      : 'The AI operating system for business productivity'
  }
}

export function createDefaultCoverLetterData(
  personal: PersonalProfile,
  language: DocumentLanguage
): CoverLetterData {
  const isFr = language === 'fr'

  return {
    achievements: isFr
      ? [
          'Amélioration mesurable des performances opérationnelles (+25%) sur mes précédents projets.',
          'Maîtrise complète des outils numériques et excellente capacité d’adaptation.'
        ]
      : [
          'Delivered +25% operational efficiency gains across prior cross-functional initiatives.',
          'Strong track record of execution, stakeholder communication, and technical adaptability.'
        ],
    bodyParagraphs: isFr
      ? [
          'Au cours de mon parcours, j’ai développé une solide expertise dans le pilotage de projets et la résolution de problématiques complexes, tout en veillant à la qualité des livrables et au respect des délais.',
          'Intégrer votre équipe représente pour moi l’opportunité de mettre mes compétences directement au service de vos objectifs de croissance.'
        ]
      : [
          'Throughout my career, I have built a strong track record of leading complex initiatives, optimizing workflows, and delivering measurable outcomes on schedule.',
          'Joining your organization would allow me to contribute immediately to your team’s strategic objectives.'
        ],
    closing: isFr
      ? 'Dans l’attente de l’opportunité d’échanger avec vous lors d’un entretien, je vous prie d’agréer, Madame, Monsieur, l’expression de mes salutations distinguées.'
      : 'Thank you for your time and consideration. I look forward to the opportunity to discuss how my background aligns with your needs.',
    companyAddress: 'Douala, Cameroun [to confirm]',
    companyName: isFr ? 'Entreprise Cible [to confirm]' : 'Target Company [to confirm]',
    date: todayIso(),
    jobTitle: personal.headline || (isFr ? 'Poste visé [to confirm]' : 'Target Role [to confirm]'),
    linkedCvId: '',
    opening: isFr
      ? 'Madame, Monsieur, c’est avec un vif intérêt que je vous soumets ma candidature pour le poste mentionné en objet.'
      : 'Dear Hiring Manager, I am writing to express my strong interest in the position referenced above.',
    recipientName: isFr ? 'Responsable du Recrutement' : 'Hiring Manager',
    recipientTitle: isFr ? 'Direction des Ressources Humaines' : 'Human Resources Department',
    senderEmail: personal.email || 'contact@example.com',
    senderLocation: personal.location || 'Douala, Cameroun',
    senderName: personal.fullName || (isFr ? 'Nom Prénom [to confirm]' : 'Full Name [to confirm]'),
    senderPhone: personal.phone || '+237 600 00 00 00',
    senderTitle: personal.headline || '',
    tone: 'professional'
  }
}

export function createDefaultAttestationData(
  profile: BusinessProfile,
  language: DocumentLanguage,
  existingCount = 0
): AttestationData {
  const isFr = language === 'fr'

  return {
    bodyText: isFr
      ? 'Nous attestons par la présente que le bénéficiaire désigné ci-dessus a exercé ses fonctions au sein de notre établissement avec compétence, assiduité et sens des responsabilités. La présente attestation lui est délivrée pour servir et valoir ce que de droit.'
      : 'We hereby certify that the individual named above has performed their duties within our organization with professionalism, diligence, and integrity. This certificate is issued to serve where required.',
    category: 'employment',
    department: isFr ? 'Direction des Opérations' : 'Operations Department',
    endDate: todayIso(),
    isCurrent: true,
    issueCity: profile.city || 'Douala',
    issueDate: todayIso(),
    issuerAddress: [profile.address, profile.city, profile.country].filter(Boolean).join(', ') || 'Douala, Cameroun',
    issuerCompany: profile.companyName || (isFr ? 'Nom de l’Entreprise [to confirm]' : 'Company Name [to confirm]'),
    issuerNiu: profile.niu || '',
    issuerRccm: profile.rccm || '',
    recipientFullName: isFr ? 'Nom et Prénom du Collaborateur [to confirm]' : 'Employee Full Name [to confirm]',
    recipientRole: isFr ? 'Fonction occupée [to confirm]' : 'Position / Role [to confirm]',
    referenceNumber: generateDocumentNumber('ATT', existingCount),
    signatoryName: profile.signatoryName || (isFr ? 'Nom du Signataire [to confirm]' : 'Authorized Signatory [to confirm]'),
    signatoryTitle: profile.signatoryTitle || (isFr ? 'Directeur Général' : 'Managing Director'),
    startDate: '2024-01-15'
  }
}

export function createDefaultScanData(
  fileName = 'scanned-document.pdf',
  mimeType = 'application/pdf',
  extractedText = ''
): ScanDocumentData {
  return {
    confidenceNote:
      'Unclear segments are marked as [illegible]. Verify all dates, names, and monetary figures against the original source.',
    editedText: extractedText,
    extractedAt: Date.now(),
    rawText: extractedText,
    sourceFileName: fileName,
    sourceMimeType: mimeType,
    structuredSummary: ''
  }
}

export function createDefaultDocument<T extends DocumentType>(
  type: T,
  language: DocumentLanguage = 'fr',
  businessProfile: BusinessProfile = DEFAULT_BUSINESS_PROFILE,
  personalProfile: PersonalProfile = DEFAULT_PERSONAL_PROFILE,
  templateId?: string,
  existingCount = 0
): BusinessDocument<T> {
  const now = Date.now()
  const id = `doc-${type}-${now}-${Math.random().toString(36).slice(2, 7)}`
  const isFr = language === 'fr'

  const defaultTitles: Record<DocumentType, string> = {
    attestation: isFr ? 'Attestation de Travail' : 'Employment Certificate',
    contract: isFr ? 'Contrat de Prestation de Services' : 'Professional Services Agreement',
    cv: personalProfile.fullName
      ? `CV — ${personalProfile.fullName}`
      : isFr
        ? 'CV Professionnel'
        : 'Professional CV',
    deck: businessProfile.companyName
      ? `Pitch Deck — ${businessProfile.companyName}`
      : 'Investor Pitch Deck',
    invoice: isFr ? 'Facture Commerciale' : 'Commercial Invoice',
    letter: isFr ? 'Lettre de Motivation' : 'Cover Letter',
    plan: businessProfile.companyName
      ? `Business Plan — ${businessProfile.companyName}`
      : 'Business Plan',
    quote: isFr ? 'Devis Commercial' : 'Commercial Quotation',
    scan: isFr ? 'Document Scanné (OCR)' : 'Scanned Document (OCR)'
  }

  const defaultTemplateIds: Record<DocumentType, string> = {
    attestation: 'attestation-official',
    contract: 'contract-standard',
    cv: 'modern',
    deck: 'deck-venture',
    invoice: 'invoice-ohada',
    letter: 'letter-formal',
    plan: 'plan-investor',
    quote: 'quote-standard',
    scan: 'scan-default'
  }

  let data: unknown

  switch (type) {
    case 'cv':
      data = createDefaultCVData(personalProfile, language)

      break

    case 'invoice':
      data = createDefaultInvoiceData(businessProfile, language, existingCount)

      break

    case 'quote':
      data = createDefaultQuoteData(businessProfile, language, existingCount)

      break

    case 'contract':
      data = createDefaultContractData(businessProfile, language)

      break

    case 'plan':
      data = createDefaultBusinessPlanData(businessProfile, language)

      break

    case 'deck':
      data = createDefaultPitchDeckData(businessProfile, language)

      break

    case 'letter':
      data = createDefaultCoverLetterData(personalProfile, language)

      break

    case 'attestation':
      data = createDefaultAttestationData(businessProfile, language, existingCount)

      break

    case 'scan':
      data = createDefaultScanData()

      break
  }

  return {
    createdAt: now,
    data: data as BusinessDocument<T>['data'],
    id,
    language,
    status: 'draft',
    templateId: templateId || defaultTemplateIds[type],
    title: defaultTitles[type],
    type,
    updatedAt: now
  }
}

export interface DocumentValidationResult {
  errors: string[]
  valid: boolean
  warnings: string[]
}

export function validateDocument(doc: BusinessDocument): DocumentValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (!doc.title.trim()) {
    errors.push('Document title is required.')
  }

  const serialized = JSON.stringify(doc.data)

  if (serialized.includes('[to confirm]')) {
    warnings.push('Document contains [to confirm] placeholders that should be reviewed before final distribution.')
  }

  if (serialized.includes('[illegible]')) {
    warnings.push('Document contains [illegible] markers from OCR extraction.')
  }

  if (doc.type === 'invoice') {
    const inv = doc.data as InvoiceData

    if (!inv.invoiceNumber.trim()) {
      errors.push('Invoice number is required.')
    }

    if (inv.items.length === 0) {
      errors.push('At least one invoice line item is required.')
    }
  } else if (doc.type === 'quote') {
    const qt = doc.data as QuoteData

    if (!qt.quoteNumber.trim()) {
      errors.push('Quotation number is required.')
    }

    if (qt.items.length === 0) {
      errors.push('At least one quotation line item is required.')
    }
  } else if (doc.type === 'cv') {
    const cv = doc.data as CVData

    if (!cv.fullName.trim()) {
      errors.push('Candidate full name is required.')
    }
  } else if (doc.type === 'deck') {
    const deck = doc.data as PitchDeckData

    if (deck.slides.length === 0) {
      errors.push('Pitch deck must contain at least one slide.')
    }
  }

  return {
    errors,
    valid: errors.length === 0,
    warnings
  }
}
