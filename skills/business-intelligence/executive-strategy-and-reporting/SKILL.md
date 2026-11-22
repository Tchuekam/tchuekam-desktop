---
name: executive-strategy-and-reporting
description: End-to-end Business Intelligence, market research, strategic planning (SWOT, Porter's 5 Forces, PESTEL, TAM/SAM/SOM), financial & unit-economics modeling, KPI reporting, and executive/board/government deliverable synthesis.
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [business-intelligence, strategy, finance, market-intelligence, reporting, deliverable]
    related_skills: [3-statement-model, dcf-model, comps-analysis, excel-author, pptx-author]
---

# Executive Strategy, Market Intelligence & Business Reporting

Use this skill whenever the user requests a business report, strategic plan, market analysis, investor/fundraising brief, financial/operational assessment, or government policy & economic briefing.

## Autonomous Execution Protocol

1. **Plan & Decompose (`autonomous_plan`)**
   - Start complex multi-step business deliverables by creating a recoverable execution plan:
     `autonomous_plan(action="create", objective=..., steps=[...])`
   - Identify local documents in the user's workspace first using `search_files` and extract them with `read_document` (supports `.docx`, `.xlsx`, `.pptx`, `.pdf`, `.rtf`, `.csv`, and OCR images offline).
   - When online, augment with live market data via `web_search` and `web_extract`. When offline, synthesize from local workspace documents, local memory (`memory`), and session history (`session_search`).

2. **Analytical Frameworks to Apply**
   - **Executive Summary**: Bottom-Line Up Front (BLUF) — core thesis, quantified impact, key recommendations, and decision timeline.
   - **Market & Competitive Intelligence**: TAM / SAM / SOM sizing, market growth drivers, competitor positioning matrix, and regulatory/macro (PESTEL) factors.
   - **Strategic Positioning**: SWOT analysis, Porter's Five Forces, value proposition canvas, and defensibility / moat analysis.
   - **Financial & Operational Model**: Revenue drivers, unit economics (CAC, LTV, LTV/CAC, payback period, gross margin), 3-scenario projection (Conservative / Base / Aggressive), and KPI scorecard.
   - **Action Roadmap & Risk Matrix**: Phased execution timeline (30 / 60 / 90 days or Q1–Q4), resource allocation, and concrete risk mitigation controls.

3. **Deliverable Generation & Verification**
   - Produce the final formatted deliverable on disk using `autonomous_plan(action="synthesize_deliverable", output_path=..., title=..., sections=[...])` or `write_file` (supporting `.md`, `.docx`, `.html`, `.json`).
   - Always verify that the output file exists on disk and is non-empty using `autonomous_plan(action="verify")` before presenting completion to the user.
