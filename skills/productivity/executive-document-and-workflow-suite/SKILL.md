---
name: executive-document-and-workflow-suite
description: End-to-end Productivity suite for authoring professional documents (.docx, .md, .html, .pdf), spreadsheets (.xlsx, .csv), presentations (.pptx), executive communications, and structured action plans.
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [productivity, documents, docx, spreadsheets, presentations, executive-workflows]
    related_skills: [excel-author, pptx-author, powerpoint, nano-pdf]
---

# Executive Productivity: Document, Spreadsheet & Presentation Suite

Use this skill whenever the user needs polished documents, Word files (`.docx`), spreadsheets (`.xlsx`/`.csv`), presentations (`.pptx`), meeting briefs, or operational templates produced and verified on disk.

## Production Workflow

1. **Read Existing Workspace Assets First**
   - Use `read_document` to extract text, tables, and structure from existing `.docx`, `.xlsx`, `.pptx`, `.pdf`, or `.rtf` files in the user's workspace so new deliverables preserve terminology, branding, and context.

2. **Deliverable Generation**
   - **Word / Executive Reports (`.docx`, `.md`, `.html`)**: Use `autonomous_plan(action="synthesize_deliverable", output_path="...", title="...", sections=[...])` to generate a verified `.docx`, `.html`, or `.md` deliverable directly on disk.
   - **Spreadsheets (`.xlsx`, `.csv`)**: Load `excel-author` or use `execute_code` with `openpyxl` / `csv` to build multi-sheet workbooks with formatted headers, formulas, and summary tables.
   - **Presentations (`.pptx`)**: Load `pptx-author` or `powerpoint` to generate structured slide decks.

3. **Mandatory Verification**
   - Every generated productivity file must be verified on disk for existence and non-zero size before reporting completion.
