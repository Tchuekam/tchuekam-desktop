export type BuilderId = 'cv' | 'invoice' | 'contract' | 'deck' | 'plan' | 'quote' | 'letter' | 'attestation'

// Added to every builder prompt: drafts must not invent facts, and the assistant
// writes in the language the user writes in.
const GROUNDING_RULE =
  'Do not invent names, dates, amounts or legal terms: mark anything I did not give you as [to confirm]. Write in the language I use.'

const withGrounding = (task: string) => `${task} ${GROUNDING_RULE}`

// Prompts seeded into the chat composer. They are never sent automatically, so
// the user can edit them, attach files and send when ready.
export const BUILDER_PROMPTS: Record<BuilderId, string> = {
  cv: withGrounding(
    'Help me write an ATS-friendly CV (résumé). Ask me one question at a time about my experience, education, skills and target role, then draft the full CV.'
  ),
  invoice: withGrounding(
    'Help me create an invoice (facture) in FCFA. Ask me for the seller and client details, the items with quantities and prices, any tax, and the payment method (MoMo, Orange Money or bank transfer). Then draft the complete invoice.'
  ),
  contract: withGrounding(
    'Help me draft a contract (contrat). Ask me whether it is a service agreement, a lease (bail) or an NDA, then ask for the parties, scope, duration, payment terms and any special clauses. Then draft the full contract and point out the clauses a lawyer should review.'
  ),
  deck: withGrounding(
    'Help me build an investor pitch deck. Ask me about the problem, the solution, the market, traction, the business model, the team and the amount I am raising. Then outline the slides and write the content for each one.'
  ),
  plan: withGrounding(
    'Help me write a business plan with its key financial assumptions. Ask me about the business, the market, the offer, the team and the funding needed. Then draft each section, with revenue, cost and cash-flow assumptions in FCFA unless I say otherwise, labelled as illustrative estimates.'
  ),
  quote: withGrounding(
    'Help me create a quotation (devis). Ask me for the client, the services or products, quantities, unit prices, validity period and payment terms. Then draft the complete quote in FCFA.'
  ),
  letter: withGrounding(
    'Help me write a cover letter (lettre de motivation). Ask me which language I want (French or English), the job and company, and my key achievements. Then draft the letter.'
  ),
  attestation: withGrounding(
    'Help me write an attestation (employment or internship certificate). Ask me who issues it, who it is for, and the role and dates. Then draft the attestation, ready for my review.'
  )
}

export const NEW_DOCUMENT_PROMPT =
  'Help me create a business document. Ask me which type I need: CV, invoice, contract, pitch deck, business plan, quote, cover letter or attestation. Then guide me step by step until it is finished.'

export const SCAN_TO_TEXT_PROMPT =
  'Convert the photos or PDFs I attach into text. Extract the text from each file, keep the layout where you can, and show me the result for each one. If a file has no readable text, say so. Mark unclear text as [illegible] and never guess amounts, names or dates. Then ask me what to do with it next.'
