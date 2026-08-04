/**
 * TchueKAM Image Studio v2 — Color Palette Extraction Engine
 */

export function extractColorPalette(imageSrc: string): Promise<string[]> {
  return new Promise(resolve => {
    const img = new Image()
    img.crossOrigin = 'Anonymous'
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = 100
      canvas.height = 100
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        resolve(['#1A1A2E', '#16213E', '#0F3460', '#E94560', '#FFFFFF'])
        return
      }

      ctx.drawImage(img, 0, 0, 100, 100)
      const data = ctx.getImageData(0, 0, 100, 100).data
      const hexMap: Record<string, number> = {}

      for (let i = 0; i < data.length; i += 16) {
        const r = data[i]
        const g = data[i + 1]
        const b = data[i + 2]
        const hex = `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`
        hexMap[hex] = (hexMap[hex] || 0) + 1
      }

      const sorted = Object.keys(hexMap).sort((a, b) => hexMap[b] - hexMap[a])
      resolve(sorted.slice(0, 5))
    }
    img.onerror = () => {
      resolve(['#1A1A2E', '#16213E', '#0F3460', '#E94560', '#FFFFFF'])
    }
    img.src = imageSrc
  })
}
