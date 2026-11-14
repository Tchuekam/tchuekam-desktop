import { validateDocument } from '../schemas'
import type { BusinessDocument, ExportFormat } from '../types'

import { buildDocxBytes, buildPptxBytes, buildXlsxBytes } from './ooxml-builders'
import { buildPdfBytes } from './pdf-builder'

export interface ExportBusinessDocumentOptions {
  triggerDownload?: boolean
}

export interface ExportBusinessDocumentResult {
  blob: Blob
  bytes: Uint8Array
  filename: string
  format: ExportFormat
  mimeType: string
  warnings: string[]
}

const MIME_TYPES: Record<ExportFormat, string> = {
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
}

function sanitizeExportFilename(title: string, format: ExportFormat): string {
  const safeBase =
    Array.from((title || 'document').normalize('NFC'))
      .filter(ch => ch.charCodeAt(0) >= 32)
      .join('')
      .replace(/[<>:"/\\|?*]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 80) || 'document'

  return `${safeBase}.${format}`
}

/**
 * Validate and serialize a BusinessDocument into downloadable PDF, DOCX, XLSX, or PPTX binary bytes.
 */
export function exportBusinessDocument(
  doc: BusinessDocument,
  format: ExportFormat,
  options?: ExportBusinessDocumentOptions
): ExportBusinessDocumentResult {
  const validation = validateDocument(doc)

  if (!validation.valid) {
    throw new Error(validation.errors.join(' '))
  }

  let bytes: Uint8Array

  switch (format) {
    case 'pdf':
      bytes = buildPdfBytes(doc)

      break

    case 'docx':
      bytes = buildDocxBytes(doc)

      break

    case 'xlsx':
      bytes = buildXlsxBytes(doc)

      break

    case 'pptx':
      bytes = buildPptxBytes(doc)

      break
  }

  const mimeType = MIME_TYPES[format]
  const filename = sanitizeExportFilename(doc.title, format)
  const blob = new Blob([bytes.buffer as ArrayBuffer], { type: mimeType })

  if (options?.triggerDownload !== false && typeof document !== 'undefined') {
    try {
      const url = URL.createObjectURL?.(blob)

      if (url) {
        const anchor = document.createElement('a')

        anchor.href = url
        anchor.download = filename
        anchor.style.display = 'none'
        document.body.appendChild(anchor)
        anchor.click()
        document.body.removeChild(anchor)
        window.setTimeout(() => URL.revokeObjectURL?.(url), 2000)
      }
    } catch {
      // Ignore DOM download failures in headless/test environments
    }
  }

  return {
    blob,
    bytes,
    filename,
    format,
    mimeType,
    warnings: validation.warnings
  }
}
