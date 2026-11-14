export interface ZipEntryInput {
  content: string | Uint8Array
  path: string
}

const CRC32_TABLE: Uint32Array = (() => {
  const table = new Uint32Array(256)

  for (let i = 0; i < 256; i++) {
    let crc = i

    for (let bit = 0; bit < 8; bit++) {
      crc = crc & 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1
    }

    table[i] = crc >>> 0
  }

  return table
})()

function computeCrc32(bytes: Uint8Array): number {
  let crc = 0xffffffff

  for (let i = 0; i < bytes.length; i++) {
    const byte = bytes[i] ?? 0

    crc = (CRC32_TABLE[(crc ^ byte) & 0xff] ?? 0) ^ (crc >>> 8)
  }

  return (crc ^ 0xffffffff) >>> 0
}

/**
 * Escape XML special characters so arbitrary user text renders safely inside OOXML parts.
 */
export function escapeXml(value: string): string {
  return (value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

/**
 * Build an uncompressed (STORE) PKZIP container in pure TypeScript for DOCX, XLSX, and PPTX exports.
 */
export function createZipArchive(entries: ZipEntryInput[]): Uint8Array {
  const encoder = new TextEncoder()
  const localParts: Uint8Array[] = []
  const centralParts: Uint8Array[] = []
  let localOffset = 0

  for (const entry of entries) {
    const nameBytes = encoder.encode(entry.path.replace(/^\/+/, ''))
    const dataBytes = typeof entry.content === 'string' ? encoder.encode(entry.content) : entry.content
    const crc = computeCrc32(dataBytes)
    const size = dataBytes.length

    const localHeader = new Uint8Array(30 + nameBytes.length)
    const localView = new DataView(localHeader.buffer)

    localView.setUint32(0, 0x04034b50, true)
    localView.setUint16(4, 20, true)
    localView.setUint16(6, 2048, true)
    localView.setUint16(8, 0, true)
    localView.setUint16(10, 0, true)
    localView.setUint16(12, 33, true)
    localView.setUint32(14, crc, true)
    localView.setUint32(18, size, true)
    localView.setUint32(22, size, true)
    localView.setUint16(26, nameBytes.length, true)
    localView.setUint16(28, 0, true)
    localHeader.set(nameBytes, 30)
    localParts.push(localHeader, dataBytes)

    const centralHeader = new Uint8Array(46 + nameBytes.length)
    const centralView = new DataView(centralHeader.buffer)

    centralView.setUint32(0, 0x02014b50, true)
    centralView.setUint16(4, 20, true)
    centralView.setUint16(6, 20, true)
    centralView.setUint16(8, 2048, true)
    centralView.setUint16(10, 0, true)
    centralView.setUint16(12, 0, true)
    centralView.setUint16(14, 33, true)
    centralView.setUint32(16, crc, true)
    centralView.setUint32(20, size, true)
    centralView.setUint32(24, size, true)
    centralView.setUint16(28, nameBytes.length, true)
    centralView.setUint16(30, 0, true)
    centralView.setUint16(32, 0, true)
    centralView.setUint16(34, 0, true)
    centralView.setUint16(36, 0, true)
    centralView.setUint32(38, 0, true)
    centralView.setUint32(42, localOffset, true)
    centralHeader.set(nameBytes, 46)
    centralParts.push(centralHeader)

    localOffset += localHeader.length + dataBytes.length
  }

  let centralSize = 0

  for (const part of centralParts) {
    centralSize += part.length
  }

  const endRecord = new Uint8Array(22)
  const endView = new DataView(endRecord.buffer)

  endView.setUint32(0, 0x06054b50, true)
  endView.setUint16(4, 0, true)
  endView.setUint16(6, 0, true)
  endView.setUint16(8, entries.length, true)
  endView.setUint16(10, entries.length, true)
  endView.setUint32(12, centralSize, true)
  endView.setUint32(16, localOffset, true)
  endView.setUint16(20, 0, true)

  const archive = new Uint8Array(localOffset + centralSize + endRecord.length)
  let cursor = 0

  for (const part of localParts) {
    archive.set(part, cursor)
    cursor += part.length
  }

  for (const part of centralParts) {
    archive.set(part, cursor)
    cursor += part.length
  }

  archive.set(endRecord, cursor)

  return archive
}
