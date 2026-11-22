---
name: document-extraction-and-ocr-analytics
description: Data Intelligence workflow for multi-format document extraction (PDF, DOCX, XLSX, PPTX, RTF, CSV, HTML), offline/online OCR, structured data normalization, cross-document reconciliation, and analytical reporting.
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [data-intelligence, ocr, document-analysis, data-extraction, structured-reporting]
    related_skills: [ocr-and-documents, nano-pdf, ml-best-practices]
---

# Data Intelligence: Document Extraction, OCR & Structured Analytics

Use this skill when extracting structured data from documents, spreadsheets, PDFs, scanned images, or multi-file data rooms (Works 100% offline and online).

## Core Workflow

1. **Unified Document Ingestion (`read_document`)**
   - Use `read_document(path=..., max_chars=..., ocr=True)` as the primary tool for `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.rtf`, `.csv`, `.tsv`, `.html`, and scanned image files (`.png`, `.jpg`, `.webp`, `.tiff`).
   - Note: If `read_file` is called on a binary document format, TchuekaM's self-healing engine automatically routes it to `read_document`.

2. **Structured Extraction & Normalization**
   - For tabular datasets (`.xlsx`, `.csv`, `.tsv`), inspect sheet names, column headers, row counts, and missing-value ratios.
   - When aggregating across large spreadsheets or multiple files, use `execute_code` or `terminal` (Python with `openpyxl`, `csv`, `json`, `sqlite3`, or `pandas`) to compute exact totals, distributions, and cross-tabulations — never estimate arithmetic mentally.

3. **Verification & Output Delivery**
   - Export cleaned datasets or structured intelligence reports to disk (`.json`, `.csv`, `.md`, `.docx`, `.html`) and verify file existence and byte size via `autonomous_plan(action="verify")` or `self_inspect(aspect="deliverables")`.
