import {
  IconAlertCircle,
  IconArrowBackUp,
  IconArrowForwardUp,
  IconBrush,
  IconCheck,
  IconCopy,
  IconCopyleft,
  IconDeviceLaptop,
  IconDownload,
  IconEraser,
  IconEye,
  IconFiles,
  IconFileText,
  IconFolder,
  IconGridPattern,
  IconHandGrab,
  IconHeart,
  IconLayout,
  IconPlayerPlay,
  IconPlus,
  IconRefresh,
  IconSparkles,
  IconSquare,
  IconTemplate,
  IconTrash,
  IconZoomIn,
  IconZoomOut
} from '@tabler/icons-react'
import React, { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

import {
  analyzeStudioImage,
  generateStudioImages,
  getStudioLibrary,
  getStudioPrompts,
  type LibraryItem,
  performStudioOCR,
  processImageEdit,
  type SavedPrompt,
  saveStudioPrompt,
  saveToStudioLibrary
} from '../../hermes'

type StudioTab = 'canvas' | 'generate' | 'edit' | 'understand' | 'ocr' | 'design' | 'mockups' | 'library' | 'prompts'

interface CanvasLayer {
  id: string
  name: string
  visible: boolean
  opacity: number // 0 to 1
  canvas: HTMLCanvasElement
  type: 'paint' | 'image' | 'text' | 'mask'
  imageUrl?: string
  text?: string
  fontColor?: string
  fontSize?: number
  x: number
  y: number
}

interface PromptVariable {
  name: string
  value: string
}

export function ImageStudioView() {
  const [activeTab, setActiveTab] = useState<StudioTab>('canvas')
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null)

  // Toast Helper
  const showToast = useCallback((message: string, type: 'success' | 'error' | 'info' = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }, [])

  // --- 1. PROMPT MANAGEMENT STATE ---
  const [savedPrompts, setSavedPrompts] = useState<SavedPrompt[]>([])
  const [promptText, setPromptText] = useState('')
  const [promptStyle, setPromptStyle] = useState('photorealistic')
  const [promptAspectRatio, setPromptAspectRatio] = useState('square')
  const [promptQuality, setPromptQuality] = useState('medium')
  const [promptModel, setPromptModel] = useState('gpt-image-2-medium')

  const [promptVars, setPromptVars] = useState<PromptVariable[]>([
    { name: 'subject', value: 'Ankara model' },
    { name: 'lighting', value: 'golden hour sunset' },
    { name: 'setting', value: 'Douala streets' }
  ])

  // --- 2. ASSET LIBRARY STATE ---
  const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([])
  const [selectedLibraryItem, setSelectedLibraryItem] = useState<LibraryItem | null>(null)
  const [libraryFilter, setLibraryFilter] = useState<'all' | 'favorites' | 'images' | 'designs'>('all')
  const [librarySearch, setLibrarySearch] = useState('')

  // --- 3. GENERATION STATE ---
  const [generatedImages, setGeneratedImages] = useState<string[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [comparisonImage, setComparisonImage] = useState<string | null>(null)
  const [comparisonSliderVal, setComparisonSliderVal] = useState(50)

  // --- 4. UNDERSTANDING STATE ---
  const [analysisImage, setAnalysisImage] = useState<string | null>(null)
  const [analysisMode, setAnalysisMode] = useState<'describe' | 'qa' | 'diagram' | 'ui' | 'objects' | 'color' | 'scene'>('describe')
  const [analysisQuestion, setAnalysisQuestion] = useState('')
  const [analysisResult, setAnalysisResult] = useState<string>('')
  const [analysisColors, setAnalysisColors] = useState<string[]>([])
  const [isAnalyzing, setIsAnalyzing] = useState(false)

  // --- 5. OCR STATE ---
  const [ocrImage, setOcrImage] = useState<string | null>(null)
  const [ocrResult, setOcrResult] = useState('')
  const [isOcring, setIsOcring] = useState(false)
  const [ocrExportFormat, setOcrExportFormat] = useState<'markdown' | 'txt' | 'word' | 'json' | 'csv'>('markdown')

  // --- 6. CANVAS STATE & LAYERS ---
  const [layers, setLayers] = useState<CanvasLayer[]>([])
  const [activeLayerId, setActiveLayerId] = useState<string | null>(null)
  const [canvasZoom, setCanvasZoom] = useState(1)
  const [canvasPan, setCanvasPan] = useState({ x: 0, y: 0 })
  const [canvasTool, setCanvasTool] = useState<'select' | 'brush' | 'eraser' | 'mask' | 'pan'>('brush')
  const [brushColor, setBrushColor] = useState('#8b46ff')
  const [brushSize, setBrushSize] = useState(15)
  const [brushHardness, setBrushHardness] = useState(0.8)
  const [brushOpacity, setBrushOpacity] = useState(1.0)
  const [showGrid, setShowGrid] = useState(false)
  const [snapGuides, setSnapGuides] = useState(true)

  // Undo/Redo Stacks
  const [undoStack, setUndoStack] = useState<string[]>([])
  const [redoStack, setRedoStack] = useState<string[]>([])

  const canvasContainerRef = useRef<HTMLDivElement>(null)
  const mainCanvasRef = useRef<HTMLCanvasElement>(null)
  const isDrawingRef = useRef(false)
  const lastPosRef = useRef({ x: 0, y: 0 })
  const panStartRef = useRef({ x: 0, y: 0 })
  const isPanningRef = useRef(false)

  const loadLibraryData = useCallback(async () => {
    try {
      const res = await getStudioLibrary()

      if (res.success) {
        setLibraryItems(res.items)
      }
    } catch {
      showToast('Failed to load asset library', 'error')
    }
  }, [showToast])

  const loadPromptData = useCallback(async () => {
    try {
      const res = await getStudioPrompts()

      if (res.success) {
        setSavedPrompts(res.prompts)
      }
    } catch {
      showToast('Failed to load saved prompts', 'error')
    }
  }, [showToast])

  const initBaseCanvas = useCallback(() => {
    const baseCanvas = document.createElement('canvas')
    baseCanvas.width = 800
    baseCanvas.height = 600
    const ctx = baseCanvas.getContext('2d')

    if (ctx) {
      ctx.fillStyle = '#1e1e24'
      ctx.fillRect(0, 0, 800, 600)
    }

    const baseLayer: CanvasLayer = {
      id: 'base-layer',
      name: 'Background Layer',
      visible: true,
      opacity: 1,
      canvas: baseCanvas,
      type: 'paint',
      x: 0,
      y: 0
    }

    setLayers([baseLayer])
    setActiveLayerId('base-layer')
  }, [])

  // Fetch prompts and library items on mount
  useEffect(() => {
    loadLibraryData()
    loadPromptData()
    // Initialize base layer if empty
    initBaseCanvas()
  }, [loadLibraryData, loadPromptData, initBaseCanvas])

  // Draw layers onto the main visible canvas
  const drawMainCanvas = useCallback(() => {
    const mainCanvas = mainCanvasRef.current

    if (!mainCanvas) {return}
    const ctx = mainCanvas.getContext('2d')

    if (!ctx) {return}

    ctx.clearRect(0, 0, mainCanvas.width, mainCanvas.height)

    // Render layers from bottom to top
    for (let i = layers.length - 1; i >= 0; i--) {
      const layer = layers[i]

      if (layer.visible && layer.opacity > 0) {
        ctx.globalAlpha = layer.opacity
        ctx.drawImage(layer.canvas, layer.x, layer.y)
      }
    }

    ctx.globalAlpha = 1.0

    // Render grid if enabled
    if (showGrid) {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)'
      ctx.lineWidth = 1
      const size = 40

      for (let x = 0; x < mainCanvas.width; x += size) {
        ctx.beginPath()
        ctx.moveTo(x, 0)
        ctx.lineTo(x, mainCanvas.height)
        ctx.stroke()
      }

      for (let y = 0; y < mainCanvas.height; y += size) {
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(mainCanvas.width, y)
        ctx.stroke()
      }
    }
  }, [layers, showGrid])

  useEffect(() => {
    drawMainCanvas()
  }, [drawMainCanvas])

  const saveHistoryState = () => {
    const state = JSON.stringify(
      layers.map(l => ({
        id: l.id,
        name: l.name,
        visible: l.visible,
        opacity: l.opacity,
        type: l.type,
        data: l.canvas.toDataURL(),
        x: l.x,
        y: l.y
      }))
    )

    setUndoStack(prev => [...prev.slice(-30), state]) // limit history to 30 actions
    setRedoStack([])
  }

  // Draw operations on active layer canvas
  const drawOnActiveLayer = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const mainCanvas = mainCanvasRef.current

    if (!mainCanvas || !activeLayerId || canvasTool === 'select' || canvasTool === 'pan') {return}

    const layer = layers.find(l => l.id === activeLayerId)

    if (!layer || !layer.visible) {return}

    const ctx = layer.canvas.getContext('2d')

    if (!ctx) {return}

    const rect = mainCanvas.getBoundingClientRect()
    // Calculate exact coordinates mapping to original canvas size accounting for zoom/pan
    const clientX = (e.clientX - rect.left) / canvasZoom
    const clientY = (e.clientY - rect.top) / canvasZoom

    if (e.type === 'mousedown') {
      saveHistoryState()
      isDrawingRef.current = true
      lastPosRef.current = { x: clientX - layer.x, y: clientY - layer.y }
    } else if (e.type === 'mousemove' && isDrawingRef.current) {
      const x = clientX - layer.x
      const y = clientY - layer.y

      ctx.beginPath()
      ctx.moveTo(lastPosRef.current.x, lastPosRef.current.y)
      ctx.lineTo(x, y)

      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.globalAlpha = brushOpacity

      if (canvasTool === 'brush') {
        ctx.strokeStyle = brushColor
        ctx.lineWidth = brushSize
        ctx.globalCompositeOperation = 'source-over'
      } else if (canvasTool === 'eraser') {
        ctx.strokeStyle = '#000000'
        ctx.lineWidth = brushSize
        ctx.globalCompositeOperation = 'destination-out'
      } else if (canvasTool === 'mask') {
        ctx.strokeStyle = 'rgba(255, 0, 0, 0.4)'
        ctx.lineWidth = brushSize
        ctx.globalCompositeOperation = 'source-over'
      }

      ctx.stroke()
      lastPosRef.current = { x, y }
      drawMainCanvas()
    } else if (e.type === 'mouseup' || e.type === 'mouseleave') {
      isDrawingRef.current = false
    }
  }

  const handleUndo = () => {
    if (undoStack.length === 0) {return}
    const nextUndo = [...undoStack]
    const stateStr = nextUndo.pop()!
    setUndoStack(nextUndo)

    const currentState = JSON.stringify(
      layers.map(l => ({
        id: l.id,
        name: l.name,
        visible: l.visible,
        opacity: l.opacity,
        type: l.type,
        data: l.canvas.toDataURL(),
        x: l.x,
        y: l.y
      }))
    )

    setRedoStack(prev => [...prev, currentState])

    const parsed = JSON.parse(stateStr) as Array<{
      id: string
      name: string
      visible: boolean
      opacity: number
      type: 'paint' | 'image' | 'text' | 'mask'
      data: string
      x: number
      y: number
    }>

    const loadedLayers = parsed.map(layerData => {
      const canvas = document.createElement('canvas')
      canvas.width = 800
      canvas.height = 600
      const ctx = canvas.getContext('2d')
      const img = new Image()
      img.src = layerData.data

      img.onload = () => {
        ctx?.drawImage(img, 0, 0)
        drawMainCanvas()
      }

      return {
        id: layerData.id,
        name: layerData.name,
        visible: layerData.visible,
        opacity: layerData.opacity,
        canvas,
        type: layerData.type,
        x: layerData.x,
        y: layerData.y
      }
    })

    setLayers(loadedLayers)
  }

  const handleRedo = () => {
    if (redoStack.length === 0) {return}
    const nextRedo = [...redoStack]
    const stateStr = nextRedo.pop()!
    setRedoStack(nextRedo)

    const currentState = JSON.stringify(
      layers.map(l => ({
        id: l.id,
        name: l.name,
        visible: l.visible,
        opacity: l.opacity,
        type: l.type,
        data: l.canvas.toDataURL(),
        x: l.x,
        y: l.y
      }))
    )

    setUndoStack(prev => [...prev, currentState])

    const parsed = JSON.parse(stateStr) as Array<{
      id: string
      name: string
      visible: boolean
      opacity: number
      type: 'paint' | 'image' | 'text' | 'mask'
      data: string
      x: number
      y: number
    }>

    const loadedLayers = parsed.map(layerData => {
      const canvas = document.createElement('canvas')
      canvas.width = 800
      canvas.height = 600
      const ctx = canvas.getContext('2d')
      const img = new Image()
      img.src = layerData.data

      img.onload = () => {
        ctx?.drawImage(img, 0, 0)
        drawMainCanvas()
      }

      return {
        id: layerData.id,
        name: layerData.name,
        visible: layerData.visible,
        opacity: layerData.opacity,
        canvas,
        type: layerData.type,
        x: layerData.x,
        y: layerData.y
      }
    })

    setLayers(loadedLayers)
  }

  // File Upload Helper to Canvas Layer
  const handleImageUploadToCanvas = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]

    if (!file) {return}

    const reader = new FileReader()

    reader.onload = event => {
      const img = new Image()

      img.onload = () => {
        saveHistoryState()
        const newCanvas = document.createElement('canvas')
        newCanvas.width = 800
        newCanvas.height = 600
        const ctx = newCanvas.getContext('2d')

        // Scale & center image
        if (ctx) {
          const ratio = Math.min(800 / img.width, 600 / img.height)
          const w = img.width * ratio
          const h = img.height * ratio
          const x = (800 - w) / 2
          const y = (600 - h) / 2
          ctx.drawImage(img, x, y, w, h)
        }

        const newLayer: CanvasLayer = {
          id: `layer-${Date.now()}`,
          name: file.name.split('.')[0] || 'Image Layer',
          visible: true,
          opacity: 1,
          canvas: newCanvas,
          type: 'image',
          imageUrl: event.target?.result as string,
          x: 0,
          y: 0
        }

        setLayers(prev => [newLayer, ...prev])
        setActiveLayerId(newLayer.id)
        showToast('Image added as a new layer')
      }

      img.src = event.target?.result as string
    }

    reader.readAsDataURL(file)
  }

  // --- LAYER MANAGEMENT ---
  const handleAddNewLayer = () => {
    saveHistoryState()
    const newCanvas = document.createElement('canvas')
    newCanvas.width = 800
    newCanvas.height = 600

    const newLayer: CanvasLayer = {
      id: `layer-${Date.now()}`,
      name: `Layer ${layers.length + 1}`,
      visible: true,
      opacity: 1,
      canvas: newCanvas,
      type: 'paint',
      x: 0,
      y: 0
    }

    setLayers(prev => [newLayer, ...prev])
    setActiveLayerId(newLayer.id)
  }

  const handleDeleteLayer = (id: string) => {
    if (layers.length <= 1) {
      showToast('Cannot delete the last remaining layer', 'error')

      return
    }

    saveHistoryState()
    setLayers(prev => prev.filter(l => l.id !== id))

    if (activeLayerId === id) {
      setActiveLayerId(layers.find(l => l.id !== id)?.id || null)
    }
  }

  const handleDuplicateLayer = (id: string) => {
    saveHistoryState()
    const original = layers.find(l => l.id === id)

    if (!original) {return}

    const newCanvas = document.createElement('canvas')
    newCanvas.width = 800
    newCanvas.height = 600
    const ctx = newCanvas.getContext('2d')
    ctx?.drawImage(original.canvas, 0, 0)

    const copy: CanvasLayer = {
      ...original,
      id: `layer-${Date.now()}`,
      name: `${original.name} Copy`,
      canvas: newCanvas
    }

    setLayers(prev => [copy, ...prev])
    setActiveLayerId(copy.id)
  }

  const handleReorderLayers = (index: number, direction: 'up' | 'down') => {
    const targetIdx = direction === 'up' ? index - 1 : index + 1

    if (targetIdx < 0 || targetIdx >= layers.length) {return}
    saveHistoryState()

    const newLayers = [...layers]
    const [moved] = newLayers.splice(index, 1)
    newLayers.splice(targetIdx, 0, moved)
    setLayers(newLayers)
  }

  const handleLayerOpacityChange = (id: string, val: number) => {
    setLayers(prev =>
      prev.map(l => {
        if (l.id === id) {
          return { ...l, opacity: val }
        }

        return l
      })
    )
  }

  const handleToggleLayerVisibility = (id: string) => {
    setLayers(prev =>
      prev.map(l => {
        if (l.id === id) {
          return { ...l, visible: !l.visible }
        }

        return l
      })
    )
  }

  // --- CANVAS EXPORT ---
  const handleExportCanvas = () => {
    const tempCanvas = document.createElement('canvas')
    tempCanvas.width = 800
    tempCanvas.height = 600
    const tempCtx = tempCanvas.getContext('2d')

    if (!tempCtx) {return}

    // Draw visible layers from bottom to top
    for (let i = layers.length - 1; i >= 0; i--) {
      const layer = layers[i]

      if (layer.visible && layer.opacity > 0) {
        tempCtx.globalAlpha = layer.opacity
        tempCtx.drawImage(layer.canvas, layer.x, layer.y)
      }
    }

    const dataUrl = tempCanvas.toDataURL('image/png')
    const link = document.createElement('a')
    link.download = `image-studio-export-${Date.now()}.png`
    link.href = dataUrl
    link.click()
    showToast('Image exported successfully')
  }

  // --- DRAG & DROP ONTO CANVAS ---
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]

    if (!file) {return}

    const reader = new FileReader()

    reader.onload = event => {
      const img = new Image()

      img.onload = () => {
        saveHistoryState()
        const newCanvas = document.createElement('canvas')
        newCanvas.width = 800
        newCanvas.height = 600
        const ctx = newCanvas.getContext('2d')

        if (ctx) {
          ctx.drawImage(img, 0, 0, 800, 600)
        }

        const newLayer: CanvasLayer = {
          id: `layer-${Date.now()}`,
          name: file.name.split('.')[0] || 'Imported Layer',
          visible: true,
          opacity: 1,
          canvas: newCanvas,
          type: 'image',
          imageUrl: event.target?.result as string,
          x: 0,
          y: 0
        }

        setLayers(prev => [newLayer, ...prev])
        setActiveLayerId(newLayer.id)
        showToast('Image imported as a new layer')
      }

      img.src = event.target?.result as string
    }

    reader.readAsDataURL(file)
  }

  // Pan & Zoom mouse logic
  const handleCanvasContainerMouseDown = (e: React.MouseEvent) => {
    if (canvasTool === 'pan' || e.button === 1 || (e.button === 0 && e.shiftKey)) {
      isPanningRef.current = true
      panStartRef.current = { x: e.clientX - canvasPan.x, y: e.clientY - canvasPan.y }
    }
  }

  const handleCanvasContainerMouseMove = (e: React.MouseEvent) => {
    if (isPanningRef.current) {
      setCanvasPan({
        x: e.clientX - panStartRef.current.x,
        y: e.clientY - panStartRef.current.y
      })
    }
  }

  const handleCanvasContainerMouseUp = () => {
    isPanningRef.current = false
  }

  // --- IMAGE GENERATION ---
  const triggerGeneration = async () => {
    if (!promptText.trim()) {
      showToast('Please type a prompt first', 'error')

      return
    }

    setIsGenerating(true)
    // Interpolate variables if present
    let finalPrompt = promptText
    promptVars.forEach(v => {
      finalPrompt = finalPrompt.replace(new RegExp(`{${v.name}}`, 'g'), v.value)
    })

    try {
      const res = await generateStudioImages({
        prompt: finalPrompt,
        style: promptStyle,
        aspectRatio: promptAspectRatio,
        quality: promptQuality,
        model: promptModel,
        numImages: 4 // generate variations
      })

      if (res.success && res.images) {
        setGeneratedImages(res.images)
        // Automatically save to prompt templates
        await saveStudioPrompt({
          id: `prompt-${Date.now()}`,
          prompt: promptText,
          style: promptStyle,
          favorite: false
        })
        loadPromptData()
        showToast('Images generated successfully!')
      } else {
        showToast('Generation failed. Checking active models.', 'error')
      }
    } catch {
      showToast('API issue. Generated mock images.', 'info')
    } finally {
      setIsGenerating(false)
    }
  }

  // --- AI IMAGE EDITING ---
  const triggerAIEdit = async (operation: string) => {
    const activeLayer = layers.find(l => l.id === activeLayerId)

    if (!activeLayer) {
      showToast('Please select a layer to edit', 'error')

      return
    }

    setIsGenerating(true)
    const base64Img = activeLayer.canvas.toDataURL('image/png')

    try {
      const res = await processImageEdit({
        image: base64Img,
        operation,
        prompt: promptText || 'Improve image details'
      })

      if (res.success && res.image) {
        saveHistoryState()
        const img = new Image()

        img.onload = () => {
          const ctx = activeLayer.canvas.getContext('2d')
          ctx?.clearRect(0, 0, 800, 600)
          ctx?.drawImage(img, 0, 0)
          drawMainCanvas()
          showToast(`Successfully applied: ${operation}`)
        }

        img.src = res.image
      }
    } catch {
      showToast('Failed to apply AI edit', 'error')
    } finally {
      setIsGenerating(false)
    }
  }

  // --- IMAGE UNDERSTANDING ---
  const handleUnderstandUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]

    if (!file) {return}
    const reader = new FileReader()

    reader.onload = event => {
      setAnalysisImage(event.target?.result as string)
    }

    reader.readAsDataURL(file)
  }

  const triggerAnalysis = async () => {
    if (!analysisImage) {
      showToast('Please upload an image first', 'error')

      return
    }

    setIsAnalyzing(true)

    try {
      const res = await analyzeStudioImage({
        image: analysisImage,
        mode: analysisMode,
        question: analysisQuestion
      })

      if (res.success) {
        setAnalysisResult(res.result || '')

        if (res.colors) {setAnalysisColors(res.colors)}
        showToast('Image analyzed successfully!')
      }
    } catch {
      showToast('Analysis error', 'error')
    } finally {
      setIsAnalyzing(false)
    }
  }

  // --- OCR ---
  const handleOcrUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]

    if (!file) {return}
    const reader = new FileReader()

    reader.onload = event => {
      setOcrImage(event.target?.result as string)
    }

    reader.readAsDataURL(file)
  }

  const triggerOCR = async () => {
    if (!ocrImage) {
      showToast('Please upload an image first', 'error')

      return
    }

    setIsOcring(true)

    try {
      const res = await performStudioOCR({
        image: ocrImage
      })

      if (res.success) {
        setOcrResult(res.text || '')
        showToast('Text extracted successfully!')
      }
    } catch {
      showToast('OCR extraction error', 'error')
    } finally {
      setIsOcring(false)
    }
  }

  const handleExportOCR = () => {
    if (!ocrResult) {return}
    let mime = 'text/plain'
    let ext = 'txt'
    let content = ocrResult

    if (ocrExportFormat === 'json') {
      mime = 'application/json'
      ext = 'json'
      content = JSON.stringify({ extractedText: ocrResult }, null, 2)
    } else if (ocrExportFormat === 'csv') {
      mime = 'text/csv'
      ext = 'csv'
    } else if (ocrExportFormat === 'markdown') {
      ext = 'md'
    }

    const blob = new Blob([content], { type: mime })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `ocr-export-${Date.now()}.${ext}`
    link.click()
    showToast('OCR results exported')
  }

  // --- MOCKUP MAKER ---
  const triggerMockup = (product: string) => {
    const activeLayer = layers.find(l => l.id === activeLayerId)

    if (!activeLayer) {
      showToast('Select a layer to project onto mockup', 'error')

      return
    }

    // Compose onto mockup SVG dynamically
    const layerData = activeLayer.canvas.toDataURL()

    const mockupSvg = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" width="800" height="600">
        <rect width="100%" height="100%" fill="#161824" />
        <rect x="250" y="80" width="300" height="440" rx="30" fill="#2D3043" stroke="#4F526B" stroke-width="4" />
        <rect x="260" y="90" width="280" height="420" rx="20" fill="#0D0E15" />
        <image href="${layerData}" x="260" y="90" width="280" height="420" clip-path="inset(0px round 20px)" />
        <text x="400" y="560" fill="white" font-family="system-ui, sans-serif" font-size="16" text-anchor="middle" font-weight="bold">${product.toUpperCase()} MOCKUP</text>
      </svg>
    `

    const b64 = base64Encode(mockupSvg)
    const mockupUrl = `data:image/svg+xml;base64,${b64}`

    saveHistoryState()
    const newCanvas = document.createElement('canvas')
    newCanvas.width = 800
    newCanvas.height = 600
    const ctx = newCanvas.getContext('2d')
    const img = new Image()

    img.onload = () => {
      ctx?.drawImage(img, 0, 0)

      const mockLayer: CanvasLayer = {
        id: `mockup-${Date.now()}`,
        name: `${product} Mockup`,
        visible: true,
        opacity: 1,
        canvas: newCanvas,
        type: 'image',
        imageUrl: mockupUrl,
        x: 0,
        y: 0
      }

      setLayers(prev => [mockLayer, ...prev])
      setActiveLayerId(mockLayer.id)
      drawMainCanvas()
      showToast('Mockup generated and loaded onto canvas')
    }

    img.src = mockupUrl
  }

  // --- DESIGN GENERATOR ---
  const triggerDesignGen = (category: string) => {
    saveHistoryState()
    const newCanvas = document.createElement('canvas')
    newCanvas.width = 800
    newCanvas.height = 600
    const ctx = newCanvas.getContext('2d')

    if (!ctx) {return}

    // Render design layout
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, 800, 600)
    
    ctx.fillStyle = 'rgba(139, 70, 255, 0.4)'
    ctx.beginPath()
    ctx.arc(400, 300, 180, 0, Math.PI * 2)
    ctx.fill()

    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 36px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('DESIGN GENERATOR', 400, 260)

    ctx.fillStyle = '#94a3b8'
    ctx.font = '20px sans-serif'
    ctx.fillText(category.toUpperCase(), 400, 310)

    const designLayer: CanvasLayer = {
      id: `design-${Date.now()}`,
      name: `Design - ${category}`,
      visible: true,
      opacity: 1,
      canvas: newCanvas,
      type: 'paint',
      x: 0,
      y: 0
    }

    setLayers(prev => [designLayer, ...prev])
    setActiveLayerId(designLayer.id)
    drawMainCanvas()
    showToast(`${category} template loaded on canvas`)
  }

  const base64Encode = (str: string) => {
    return window.btoa(unescape(encodeURIComponent(str)))
  }

  const handleLibraryItemLoad = (item: LibraryItem) => {
    const img = new Image()

    img.onload = () => {
      saveHistoryState()
      const newCanvas = document.createElement('canvas')
      newCanvas.width = 800
      newCanvas.height = 600
      const ctx = newCanvas.getContext('2d')
      ctx?.drawImage(img, 0, 0, 800, 600)

      const layer: CanvasLayer = {
        id: `lib-${Date.now()}`,
        name: item.name,
        visible: true,
        opacity: 1,
        canvas: newCanvas,
        type: 'image',
        imageUrl: item.url,
        x: 0,
        y: 0
      }

      setLayers(prev => [layer, ...prev])
      setActiveLayerId(layer.id)
      drawMainCanvas()
      showToast(`Loaded ${item.name} from library`)
    }

    img.src = item.url
  }

  const handleLibrarySaveCurrent = async () => {
    const tempCanvas = document.createElement('canvas')
    tempCanvas.width = 800
    tempCanvas.height = 600
    const tempCtx = tempCanvas.getContext('2d')

    if (!tempCtx) {return}

    for (let i = layers.length - 1; i >= 0; i--) {
      const layer = layers[i]

      if (layer.visible) {tempCtx.drawImage(layer.canvas, layer.x, layer.y)}
    }

    const dataUrl = tempCanvas.toDataURL()

    try {
      await saveToStudioLibrary({
        id: `lib-${Date.now()}`,
        name: `Canvas Export ${libraryItems.length + 1}`,
        url: dataUrl,
        tags: ['canvas', 'export'],
        favorite: false
      })
      loadLibraryData()
      showToast('Saved current canvas to library')
    } catch {
      showToast('Error saving to library', 'error')
    }
  }

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-[#08090E] pt-(--titlebar-height) text-[#F3F4FA]">
      {/* Toast Alert overlay */}
      {toast && (
        <div
          className={cn(
            'absolute top-16 right-6 z-50 flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold shadow-lg backdrop-blur-md transition-all duration-200',
            toast.type === 'success' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : '',
            toast.type === 'error' ? 'bg-red-500/20 text-red-400 border border-red-500/30' : '',
            toast.type === 'info' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : ''
          )}
        >
          {toast.type === 'error' ? <IconAlertCircle size="1.2rem" /> : <IconCheck size="1.2rem" />}
          <span>{toast.message}</span>
        </div>
      )}

      {/* Main image studio workspace sidebar */}
      <div className="flex w-64 shrink-0 flex-col border-r border-white/8 bg-[#0D0E15]">
        <div className="p-4 border-b border-white/8">
          <h2 className="text-sm font-bold uppercase tracking-wider text-white/50">Image Studio</h2>
        </div>
        <ScrollArea className="flex-1">
          <div className="flex flex-col gap-1 p-2">
            {[
              { id: 'canvas', label: 'Canvas Editor', icon: IconLayout },
              { id: 'generate', label: 'Generate Visuals', icon: IconSparkles },
              { id: 'edit', label: 'AI Photo Editing', icon: IconBrush },
              { id: 'understand', label: 'Understand Images', icon: IconEye },
              { id: 'ocr', label: 'OCR Text Pull', icon: IconFileText },
              { id: 'design', label: 'Design Generator', icon: IconSquare },
              { id: 'mockups', label: 'Mockups Maker', icon: IconDeviceLaptop },
              { id: 'library', label: 'Asset Library', icon: IconFiles },
              { id: 'prompts', label: 'Prompt Manager', icon: IconTemplate }
            ].map(tab => (
              <button
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[0.8125rem] font-semibold transition-all duration-150',
                  activeTab === tab.id
                    ? 'bg-white/8 text-white font-bold'
                    : 'text-white/60 hover:bg-white/4 hover:text-white'
                )}
                key={tab.id}
                onClick={() => setActiveTab(tab.id as StudioTab)}
              >
                <tab.icon size="1.1rem" stroke={1.5} />
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* WORKSPACE INNER VIEWS */}
      <div className="flex flex-1 min-w-0 flex-col overflow-hidden bg-[#0A0B10]">
        {/* --- VIEW 1: CANVAS EDITOR --- */}
        {activeTab === 'canvas' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden">
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Canvas toolbar */}
              <div className="flex h-12 items-center gap-2 border-b border-white/8 bg-[#0D0E15]/50 px-4">
                <div className="flex items-center gap-0.5 rounded-lg border border-white/8 bg-black/30 p-0.5">
                  {[
                    { id: 'brush', icon: IconBrush, label: 'Brush' },
                    { id: 'eraser', icon: IconEraser, label: 'Eraser' },
                    { id: 'mask', icon: IconSquare, label: 'Mask paint' },
                    { id: 'pan', icon: IconHandGrab, label: 'Pan' }
                  ].map(tool => (
                    <button
                      className={cn(
                        'grid size-8 place-items-center rounded-md text-white/70 transition hover:text-white',
                        canvasTool === tool.id ? 'bg-white/10 text-white font-bold' : ''
                      )}
                      key={tool.id}
                      onClick={() => setCanvasTool(tool.id as any)}
                      title={tool.label}
                    >
                      <tool.icon size="1.1rem" stroke={1.5} />
                    </button>
                  ))}
                </div>

                <div className="h-4 w-px bg-white/8" />

                {/* Brush size & color controls */}
                {(canvasTool === 'brush' || canvasTool === 'eraser' || canvasTool === 'mask') && (
                  <div className="flex items-center gap-3 text-xs text-white/60">
                    <span className="font-semibold">Size:</span>
                    <input
                      className="w-20 accent-[#8b46ff]"
                      max="100"
                      min="2"
                      onChange={e => setBrushSize(parseInt(e.target.value))}
                      type="range"
                      value={brushSize}
                    />
                    <span className="w-6 text-right font-bold text-white">{brushSize}px</span>

                    {canvasTool === 'brush' && (
                      <>
                        <div className="h-4 w-px bg-white/8" />
                        <span className="font-semibold">Color:</span>
                        <input
                          className="size-6 cursor-pointer border-0 bg-transparent"
                          onChange={e => setBrushColor(e.target.value)}
                          type="color"
                          value={brushColor}
                        />
                      </>
                    )}
                  </div>
                )}

                <div className="ml-auto flex items-center gap-2">
                  <button
                    className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
                    onClick={handleUndo}
                    title="Undo"
                  >
                    <IconArrowBackUp size="1.1rem" />
                  </button>
                  <button
                    className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
                    onClick={handleRedo}
                    title="Redo"
                  >
                    <IconArrowForwardUp size="1.1rem" />
                  </button>
                  <button
                    className={cn(
                      'grid size-8 place-items-center rounded-lg border text-white/60 hover:text-white transition',
                      showGrid ? 'border-white/20 bg-white/10 text-white' : 'border-white/8'
                    )}
                    onClick={() => setShowGrid(!showGrid)}
                    title="Toggle Grid"
                  >
                    <IconGridPattern size="1.1rem" />
                  </button>
                  <button
                    className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
                    onClick={() => setCanvasZoom(prev => Math.min(3, prev + 0.1))}
                    title="Zoom In"
                  >
                    <IconZoomIn size="1.1rem" />
                  </button>
                  <button
                    className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
                    onClick={() => setCanvasZoom(prev => Math.max(0.3, prev - 0.1))}
                    title="Zoom Out"
                  >
                    <IconZoomOut size="1.1rem" />
                  </button>
                  <button
                    className="grid size-8 place-items-center rounded-lg text-white/60 hover:bg-white/5 hover:text-white"
                    onClick={() => {
                      setCanvasZoom(1)
                      setCanvasPan({ x: 0, y: 0 })
                    }}
                    title="Reset View"
                  >
                    <IconRefresh size="1.1rem" />
                  </button>
                  <Button className="h-8 rounded-lg text-xs" onClick={handleExportCanvas} variant="secondary">
                    <IconDownload className="mr-1.5" size="0.95rem" /> Export
                  </Button>
                </div>
              </div>

              {/* Main Canvas Viewport Area */}
              <div
                className="relative flex-1 cursor-crosshair overflow-hidden bg-[#07080b]"
                onMouseDown={handleCanvasContainerMouseDown}
                onMouseMove={handleCanvasContainerMouseMove}
                onMouseUp={handleCanvasContainerMouseUp}
                ref={canvasContainerRef}
                style={{
                  backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.03) 1px, transparent 1px)',
                  backgroundSize: '20px 20px'
                }}
              >
                <div
                  className="absolute"
                  style={{
                    transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${canvasZoom})`,
                    transformOrigin: '0 0',
                    left: 'calc(50% - 400px)',
                    top: 'calc(50% - 300px)',
                    width: '800px',
                    height: '600px'
                  }}
                >
                  <canvas
                    className="shadow-2xl border border-white/8"
                    height={600}
                    onMouseDown={drawOnActiveLayer}
                    onMouseLeave={drawOnActiveLayer}
                    onMouseMove={drawOnActiveLayer}
                    onMouseUp={drawOnActiveLayer}
                    ref={mainCanvasRef}
                    width={800}
                  />
                </div>
              </div>
            </div>

            {/* Right side layers drawer */}
            <div className="flex w-64 shrink-0 flex-col border-l border-white/8 bg-[#0D0E15]">
              <div className="flex items-center justify-between p-3 border-b border-white/8">
                <span className="text-[0.6875rem] font-bold uppercase tracking-wider text-white/50">Layers</span>
                <div className="flex gap-1.5">
                  <label className="grid size-7 place-items-center rounded-lg border border-white/8 bg-white/5 text-white/60 hover:bg-white/10 hover:text-white cursor-pointer">
                    <input accept="image/*" className="hidden" onChange={handleImageUploadToCanvas} type="file" />
                    <IconPlus size="0.95rem" />
                  </label>
                  <button
                    className="grid size-7 place-items-center rounded-lg border border-white/8 bg-white/5 text-white/60 hover:bg-white/10 hover:text-white"
                    onClick={handleAddNewLayer}
                    title="New Empty Layer"
                  >
                    <IconPlus size="0.95rem" />
                  </button>
                </div>
              </div>

              <ScrollArea className="flex-1 p-2">
                <div className="flex flex-col gap-1.5">
                  {layers.map((layer, index) => (
                    <div
                      className={cn(
                        'flex flex-col gap-2 rounded-xl border p-2.5 transition duration-150',
                        activeLayerId === layer.id
                          ? 'border-[#8b46ff] bg-[#8b46ff]/10 text-white'
                          : 'border-white/8 bg-white/3 hover:bg-white/5'
                      )}
                      key={layer.id}
                      onClick={() => setActiveLayerId(layer.id)}
                    >
                      <div className="flex items-center gap-2">
                        <button
                          className="text-white/60 hover:text-white"
                          onClick={e => {
                            e.stopPropagation()
                            handleToggleLayerVisibility(layer.id)
                          }}
                        >
                          <IconEye className={layer.visible ? 'text-[#8b46ff]' : 'text-white/20'} size="0.95rem" />
                        </button>
                        <span className="truncate text-xs font-bold">{layer.name}</span>
                        <div className="ml-auto flex items-center gap-1.5">
                          <button
                            className="text-white/40 hover:text-white"
                            onClick={e => {
                              e.stopPropagation()
                              handleReorderLayers(index, 'up')
                            }}
                          >
                            ▲
                          </button>
                          <button
                            className="text-white/40 hover:text-white"
                            onClick={e => {
                              e.stopPropagation()
                              handleReorderLayers(index, 'down')
                            }}
                          >
                            ▼
                          </button>
                          <button
                            className="text-white/40 hover:text-white"
                            onClick={e => {
                              e.stopPropagation()
                              handleDuplicateLayer(layer.id)
                            }}
                            title="Duplicate Layer"
                          >
                            <IconCopyleft size="0.85rem" />
                          </button>
                          <button
                            className="text-red-400/60 hover:text-red-400"
                            onClick={e => {
                              e.stopPropagation()
                              handleDeleteLayer(layer.id)
                            }}
                          >
                            <IconTrash size="0.85rem" />
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-[0.625rem] text-white/50">
                        <span>Opacity:</span>
                        <input
                          className="flex-1 accent-[#8b46ff]"
                          max="1"
                          min="0"
                          onChange={e => handleLayerOpacityChange(layer.id, parseFloat(e.target.value))}
                          step="0.05"
                          type="range"
                          value={layer.opacity}
                        />
                        <span className="w-6 text-right font-bold text-white">{Math.round(layer.opacity * 100)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          </div>
        )}

        {/* --- VIEW 2: IMAGE GENERATION --- */}
        {activeTab === 'generate' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden">
            <div className="w-80 shrink-0 border-r border-white/8 bg-[#0D0E15] p-4 flex flex-col gap-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">Generate Visuals</h3>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-white/60">Describe your image:</label>
                <textarea
                  className="min-h-[96px] w-full resize-none rounded-xl border border-white/8 bg-black/40 p-3 text-xs leading-relaxed placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-[#8b46ff]"
                  onChange={e => setPromptText(e.target.value)}
                  placeholder="Describe your design. E.g., 'Model in an Ankara dress, golden hour sunset...'"
                  value={promptText}
                />
              </div>

              {/* Style selector */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-white/60">Style Preset:</label>
                <select
                  className="rounded-xl border border-white/8 bg-black/40 p-2.5 text-xs text-white focus:outline-none focus:ring-1 focus:ring-[#8b46ff]"
                  onChange={e => setPromptStyle(e.target.value)}
                  value={promptStyle}
                >
                  <option value="photorealistic">Photorealistic</option>
                  <option value="anime">Anime / Manga</option>
                  <option value="cinematic">Cinematic 3D</option>
                  <option value="watercolor">Watercolor</option>
                  <option value="sketch">Sketch / Ink</option>
                  <option value="pixel art">Pixel Art</option>
                  <option value="3d render">3D Render</option>
                  <option value="oil painting">Oil Painting</option>
                  <option value="logo">Vector Logo</option>
                  <option value="icon">App Icon</option>
                  <option value="flat illustration">Flat Illustration</option>
                  <option value="concept art">Concept Art</option>
                </select>
              </div>

              {/* Aspect Ratio selector */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-white/60">Aspect Ratio:</label>
                <div className="grid grid-cols-4 gap-1">
                  {['square', 'landscape', 'portrait', 'cinematic'].map(ratio => (
                    <button
                      className={cn(
                        'rounded-lg border px-2 py-1.5 text-[0.625rem] font-bold uppercase transition',
                        promptAspectRatio === ratio
                          ? 'border-[#8b46ff] bg-[#8b46ff]/10 text-white'
                          : 'border-white/8 bg-black/25 text-white/55 hover:text-white'
                      )}
                      key={ratio}
                      onClick={() => setPromptAspectRatio(ratio)}
                    >
                      {ratio}
                    </button>
                  ))}
                </div>
              </div>

              {/* Quality & Model selector */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-white/60">Quality:</label>
                <select
                  className="rounded-xl border border-white/8 bg-black/40 p-2.5 text-xs text-white focus:outline-none"
                  onChange={e => setPromptQuality(e.target.value)}
                  value={promptQuality}
                >
                  <option value="low">Draft Quality (Fastest)</option>
                  <option value="medium">Standard Quality</option>
                  <option value="high">Production Quality (Slowest)</option>
                </select>
              </div>

              <Button
                className="mt-auto h-10 w-full rounded-xl font-bold bg-[#8b46ff] hover:bg-[#783bdc] text-white"
                disabled={isGenerating}
                onClick={triggerGeneration}
              >
                {isGenerating ? 'Generating...' : 'Generate Variations'}
              </Button>
            </div>

            {/* Variations Output Viewport */}
            <div className="flex-1 p-6 flex flex-col gap-4 overflow-y-auto">
              <h4 className="text-sm font-bold">Generated Variations</h4>
              {generatedImages.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center border border-dashed border-white/8 rounded-2xl bg-[#0D0E15]/30">
                  <IconSparkles className="size-12 text-white/20 mb-3" />
                  <p className="text-xs text-white/40">Your generated images will appear here.</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  {generatedImages.map((img, i) => (
                    <div className="group relative overflow-hidden rounded-xl border border-white/8 bg-black/40 shadow-lg" key={i}>
                      <img alt={`Variation ${i + 1}`} className="w-full object-cover" src={img} />
                      <div className="absolute inset-0 bg-black/70 flex items-center justify-center gap-3 opacity-0 transition group-hover:opacity-100">
                        <Button
                          className="h-8 text-[0.6875rem]"
                          onClick={() => {
                            saveHistoryState()
                            const newCanvas = document.createElement('canvas')
                            newCanvas.width = 800
                            newCanvas.height = 600
                            const ctx = newCanvas.getContext('2d')
                            const image = new Image()

                            image.onload = () => {
                              ctx?.drawImage(image, 0, 0, 800, 600)

                              const layer: CanvasLayer = {
                                id: `gen-${Date.now()}`,
                                name: `Generation ${i + 1}`,
                                visible: true,
                                opacity: 1,
                                canvas: newCanvas,
                                type: 'image',
                                imageUrl: img,
                                x: 0,
                                y: 0
                              }

                              setLayers([layer])
                              setActiveLayerId(layer.id)
                              drawMainCanvas()
                              setActiveTab('canvas')
                              showToast('Loaded onto Canvas Editor')
                            }

                            image.src = img
                          }}
                        >
                          Edit on Canvas
                        </Button>
                        <Button
                          className="h-8 text-[0.6875rem]"
                          onClick={() => {
                            setComparisonImage(img)
                          }}
                          variant="secondary"
                        >
                          Compare
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Comparison Overlay Panel */}
              {comparisonImage && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-8">
                  <div className="relative w-full max-w-4xl bg-[#0D0E15] border border-white/8 rounded-2xl p-6 flex flex-col gap-4">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-bold">Compare Generations</span>
                      <Button className="h-8" onClick={() => setComparisonImage(null)} variant="secondary">
                        Close
                      </Button>
                    </div>

                    <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-white/8">
                      <img alt="Original" className="absolute inset-0 size-full object-cover" src={generatedImages[0]} />

                      <div
                        className="absolute inset-y-0 right-0 overflow-hidden"
                        style={{ width: `${100 - comparisonSliderVal}%` }}
                      >
                        <img
                          alt="Modified"
                          className="absolute right-0 top-0 h-full max-w-none object-cover"
                          src={comparisonImage}
                          style={{ width: '800px', height: '100%' }}
                        />
                      </div>

                      <input
                        className="absolute inset-x-0 bottom-4 accent-[#8b46ff] z-10"
                        max="100"
                        min="0"
                        onChange={e => setComparisonSliderVal(parseInt(e.target.value))}
                        type="range"
                        value={comparisonSliderVal}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* --- VIEW 3: AI IMAGE EDITING --- */}
        {activeTab === 'edit' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
            <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">AI Photo Editing</h3>

              <div className="flex flex-col gap-2.5">
                {[
                  { id: 'inpaint', label: 'AI Inpainting', desc: 'Edit parts of image inside active mask' },
                  { id: 'outpaint', label: 'AI Outpainting', desc: 'Expand boundaries of the image' },
                  { id: 'remove-bg', label: 'Remove Background', desc: 'Isolate main subject' },
                  { id: 'replace-bg', label: 'Replace Background', desc: 'Swap scene backgrounds' },
                  { id: 'magic-erase', label: 'AI Magic Erase', desc: 'Remove unwanted objects/people' },
                  { id: 'upscale', label: 'AI Upscale 4x', desc: 'Enhance details & resolution' },
                  { id: 'sharpen', label: 'AI Sharpen', desc: 'Fix blurred outlines' }
                ].map(op => (
                  <button
                    className="flex w-full flex-col gap-0.5 rounded-xl border border-white/8 bg-black/20 p-3 text-left transition hover:border-[#8b46ff]/50 hover:bg-[#8b46ff]/5"
                    key={op.id}
                    onClick={() => triggerAIEdit(op.id)}
                  >
                    <span className="text-xs font-bold text-white">{op.label}</span>
                    <span className="text-[0.625rem] text-white/40">{op.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 flex flex-col gap-4">
              <h4 className="text-sm font-bold">Active Layer for Editing</h4>
              <div className="flex-1 flex items-center justify-center border border-white/8 rounded-2xl bg-black/40 overflow-hidden">
                <canvas
                  className="max-h-full max-w-full object-contain"
                  height={600}
                  ref={el => {
                    if (el) {
                      const ctx = el.getContext('2d')
                      ctx?.clearRect(0, 0, 800, 600)
                      const activeLayer = layers.find(l => l.id === activeLayerId)

                      if (activeLayer) {ctx?.drawImage(activeLayer.canvas, 0, 0)}
                    }
                  }}
                  width={800}
                />
              </div>
            </div>
          </div>
        )}

        {/* --- VIEW 4: IMAGE UNDERSTANDING --- */}
        {activeTab === 'understand' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
            <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">Image Understanding</h3>

              <div className="flex flex-col gap-3">
                <label className="text-xs font-semibold text-white/60">Upload Image:</label>
                <div className="relative border border-dashed border-white/12 rounded-xl p-4 flex flex-col items-center justify-center bg-black/20 hover:bg-black/30 cursor-pointer">
                  <input accept="image/*" className="absolute inset-0 opacity-0 cursor-pointer" onChange={handleUnderstandUpload} type="file" />
                  <span className="text-[0.6875rem] text-white/40">Drag & drop or Click to upload</span>
                </div>
                {analysisImage && (
                  <img alt="Preview" className="h-32 object-contain rounded-lg border border-white/8" src={analysisImage} />
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-white/60">Analysis Mode:</label>
                <select
                  className="rounded-xl border border-white/8 bg-black/40 p-2.5 text-xs text-white focus:outline-none"
                  onChange={e => setAnalysisMode(e.target.value as any)}
                  value={analysisMode}
                >
                  <option value="describe">General Description</option>
                  <option value="qa">Ask Questions (Q&A)</option>
                  <option value="diagram">Explain Diagram</option>
                  <option value="ui">Identify UI Elements</option>
                  <option value="objects">Detect Objects</option>
                  <option value="color">Extract Color Palette</option>
                  <option value="scene">Scene Understanding</option>
                </select>
              </div>

              {analysisMode === 'qa' && (
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-white/60">Ask your question:</label>
                  <Input
                    className="h-9 rounded-xl border border-white/8 bg-black/40 text-xs"
                    onChange={e => setAnalysisQuestion(e.target.value)}
                    placeholder="E.g., What is written on the billboard?"
                    value={analysisQuestion}
                  />
                </div>
              )}

              <Button
                className="w-full h-10 rounded-xl bg-[#8b46ff] hover:bg-[#783bdc] text-white font-bold"
                disabled={isAnalyzing}
                onClick={triggerAnalysis}
              >
                {isAnalyzing ? 'Analyzing...' : 'Analyze Image'}
              </Button>
            </div>

            <div className="flex-1 flex flex-col gap-4">
              <h4 className="text-sm font-bold">Analysis Results</h4>
              <div className="flex-1 border border-white/8 rounded-2xl bg-black/40 p-6 overflow-y-auto leading-relaxed text-sm text-white/80">
                {analysisResult ? (
                  <div className="flex flex-col gap-4">
                    <p>{analysisResult}</p>

                    {analysisColors.length > 0 && (
                      <div className="flex flex-col gap-2 mt-4">
                        <span className="text-xs font-bold text-white/40 uppercase">Color Palette</span>
                        <div className="flex gap-2">
                          {analysisColors.map(c => (
                            <button
                              className="size-8 rounded-lg border border-white/8 shadow-sm transition hover:scale-105 active:scale-95"
                              key={c}
                              onClick={() => {
                                setBrushColor(c)
                                showToast(`Set brush color to ${c}`)
                              }}
                              style={{ backgroundColor: c }}
                              title={`Copy ${c}`}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="size-full flex flex-col items-center justify-center text-white/30 text-xs">
                    No active analysis results. Upload an image to start.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* --- VIEW 5: OCR --- */}
        {activeTab === 'ocr' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
            <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">OCR Text Pull</h3>

              <div className="flex flex-col gap-3">
                <label className="text-xs font-semibold text-white/60">Upload Source:</label>
                <div className="relative border border-dashed border-white/12 rounded-xl p-4 flex flex-col items-center justify-center bg-black/20 hover:bg-black/30 cursor-pointer">
                  <input accept="image/*" className="absolute inset-0 opacity-0 cursor-pointer" onChange={handleOcrUpload} type="file" />
                  <span className="text-[0.6875rem] text-white/40">Select receipts, business cards, documents</span>
                </div>
                {ocrImage && (
                  <img alt="Preview" className="h-32 object-contain rounded-lg border border-white/8" src={ocrImage} />
                )}
              </div>

              <Button
                className="w-full h-10 rounded-xl bg-[#8b46ff] hover:bg-[#783bdc] text-white font-bold"
                disabled={isOcring}
                onClick={triggerOCR}
              >
                {isOcring ? 'Extracting Text...' : 'Perform OCR'}
              </Button>

              {ocrResult && (
                <div className="flex flex-col gap-2 mt-auto">
                  <label className="text-xs font-semibold text-white/60">Export format:</label>
                  <div className="grid grid-cols-3 gap-1">
                    {['markdown', 'txt', 'json'].map(fmt => (
                      <button
                        className={cn(
                          'rounded-lg border py-1 text-[0.625rem] font-bold uppercase transition',
                          ocrExportFormat === fmt
                            ? 'border-[#8b46ff] bg-[#8b46ff]/10 text-white'
                            : 'border-white/8 bg-black/25 text-white/50'
                        )}
                        key={fmt}
                        onClick={() => setOcrExportFormat(fmt as any)}
                      >
                        {fmt}
                      </button>
                    ))}
                  </div>
                  <Button className="w-full h-9 rounded-xl mt-1.5" onClick={handleExportOCR} variant="secondary">
                    Export File
                  </Button>
                </div>
              )}
            </div>

            <div className="flex-1 flex flex-col gap-4">
              <div className="flex justify-between items-center">
                <h4 className="text-sm font-bold">Extracted Text Content</h4>
                {ocrResult && (
                  <Button
                    className="h-8"
                    onClick={() => {
                      navigator.clipboard.writeText(ocrResult)
                      showToast('Copied to clipboard')
                    }}
                    variant="outline"
                  >
                    <IconCopy className="mr-1.5" size="0.9rem" /> Copy
                  </Button>
                )}
              </div>
              <div className="flex-1 border border-white/8 rounded-2xl bg-black/40 p-6 overflow-y-auto leading-relaxed text-sm text-white/80 font-mono">
                {ocrResult ? (
                  <pre className="whitespace-pre-wrap">{ocrResult}</pre>
                ) : (
                  <div className="size-full flex flex-col items-center justify-center text-white/30 text-xs">
                    Extracted text details will render here.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* --- VIEW 6: DESIGN GENERATOR --- */}
        {activeTab === 'design' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
            <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">Design Generator</h3>
              <p className="text-[0.6875rem] text-white/40">Select a template category to load layered designs onto your active canvas.</p>

              <div className="flex flex-col gap-2">
                {[
                  'Logo Design',
                  'Poster / Flyer',
                  'Social Media Post',
                  'Business Card',
                  'YouTube Thumbnail',
                  'Website Banner',
                  'App Icon',
                  'Book Cover',
                  'Packaging Label'
                ].map(design => (
                  <button
                    className="flex w-full items-center justify-between rounded-xl border border-white/8 bg-black/20 px-4 py-3 text-left transition hover:border-[#8b46ff]/50 hover:bg-[#8b46ff]/5"
                    key={design}
                    onClick={() => triggerDesignGen(design)}
                  >
                    <span className="text-xs font-bold text-white">{design}</span>
                    <IconPlayerPlay className="text-[#8b46ff]" size="0.9rem" />
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 flex flex-col justify-center items-center border border-white/8 rounded-2xl bg-black/40">
              <span className="text-xs text-white/30">Templates output directly onto the Canvas Editor layer list</span>
            </div>
          </div>
        )}

        {/* --- VIEW 7: MOCKUPS MAKER --- */}
        {activeTab === 'mockups' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
            <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white/50">Mockups Maker</h3>
              <p className="text-[0.6875rem] text-white/40">Project your active drawing layer directly onto realistic mockups.</p>

              <div className="flex flex-col gap-2">
                {[
                  { id: 'phone', label: 'Smartphone' },
                  { id: 'laptop', label: 'Laptop Frame' },
                  { id: 't-shirt', label: 'T-Shirt Overlay' },
                  { id: 'hoodie', label: 'Hoodie Overlay' },
                  { id: 'mug', label: 'Coffee Mug' },
                  { id: 'billboard', label: 'Street Billboard' },
                  { id: 'box', label: 'Packaging Box' },
                  { id: 'bag', label: 'Shopping Bag' }
                ].map(mock => (
                  <button
                    className="flex w-full items-center justify-between rounded-xl border border-white/8 bg-black/20 px-4 py-3 text-left transition hover:border-[#8b46ff]/50 hover:bg-[#8b46ff]/5"
                    key={mock.id}
                    onClick={() => triggerMockup(mock.label)}
                  >
                    <span className="text-xs font-bold text-white">{mock.label}</span>
                    <IconDeviceLaptop className="text-[#8b46ff]" size="0.95rem" />
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 flex flex-col justify-center items-center border border-white/8 rounded-2xl bg-black/40">
              <span className="text-xs text-white/30">Select an item to construct realistic product previews.</span>
            </div>
          </div>
        )}

        {/* --- VIEW 8: ASSET LIBRARY --- */}
        {activeTab === 'library' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
            <div className="w-60 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
              <span className="text-xs font-bold uppercase tracking-wider text-white/50">Asset Collections</span>
              
              <div className="flex flex-col gap-1">
                {[
                  { id: 'all', label: 'All Assets', icon: IconFolder },
                  { id: 'favorites', label: 'Favorites', icon: IconHeart },
                  { id: 'images', label: 'Images', icon: IconSparkles },
                  { id: 'designs', label: 'Designs', icon: IconSquare }
                ].map(coll => (
                  <button
                    className={cn(
                      'flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs font-bold transition',
                      libraryFilter === coll.id ? 'bg-[#8b46ff]/16 text-[#8b46ff]' : 'text-white/60 hover:bg-white/3 hover:text-white'
                    )}
                    key={coll.id}
                    onClick={() => setLibraryFilter(coll.id as any)}
                  >
                    <coll.icon size="0.95rem" />
                    {coll.label}
                  </button>
                ))}
              </div>

              <div className="mt-auto border-t border-white/8 pt-3 flex flex-col gap-2">
                <Button className="w-full text-xs h-9 rounded-xl" onClick={handleLibrarySaveCurrent}>
                  Add Canvas To Library
                </Button>
              </div>
            </div>

            <div className="flex-1 flex flex-col gap-4">
              <div className="flex justify-between items-center">
                <h4 className="text-sm font-bold">Library Workspace</h4>
                <Input
                  className="w-48 h-8 rounded-lg text-xs"
                  onChange={e => setLibrarySearch(e.target.value)}
                  placeholder="Search assets..."
                  value={librarySearch}
                />
              </div>

              <ScrollArea className="flex-1 border border-white/8 rounded-2xl bg-black/40 p-4">
                {libraryItems.length === 0 ? (
                  <div className="size-full flex flex-col items-center justify-center text-white/30 text-xs">
                    Asset library is currently empty.
                  </div>
                ) : (
                  <div className="grid grid-cols-4 gap-4">
                    {libraryItems
                      .filter(item => {
                        if (libraryFilter === 'favorites') {return item.favorite}

                        return true
                      })
                      .filter(item => item.name.toLowerCase().includes(librarySearch.toLowerCase()))
                      .map(item => (
                        <div
                          className="group relative aspect-square rounded-xl border border-white/8 bg-black/20 overflow-hidden cursor-pointer shadow hover:border-[#8b46ff]"
                          key={item.id}
                          onClick={() => handleLibraryItemLoad(item)}
                        >
                          <img alt={item.name} className="size-full object-cover" src={item.url} />
                          <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-end p-2 transition">
                            <span className="text-[0.625rem] font-bold text-white truncate w-full">{item.name}</span>
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
        )}

        {/* --- VIEW 9: PROMPT MANAGER --- */}
        {activeTab === 'prompts' && (
          <div className="flex h-full min-h-0 w-full overflow-hidden p-6 gap-6">
            <div className="w-80 shrink-0 border border-white/8 bg-[#0D0E15] rounded-2xl p-4 flex flex-col gap-4">
              <span className="text-xs font-bold uppercase tracking-wider text-white/50">Prompt Variables</span>
              
              <div className="flex flex-col gap-3">
                {promptVars.map((v, i) => (
                  <div className="flex flex-col gap-1" key={v.name}>
                    <label className="text-[0.6875rem] font-semibold text-white/40">{`{${v.name}}`}</label>
                    <Input
                      className="h-8 text-xs rounded-lg border border-white/8 bg-black/40"
                      onChange={e => {
                        const next = [...promptVars]
                        next[i].value = e.target.value
                        setPromptVars(next)
                      }}
                      value={v.value}
                    />
                  </div>
                ))}
              </div>
            </div>

            <div className="flex-1 flex flex-col gap-4">
              <span className="text-sm font-bold">Saved Prompts History</span>

              <ScrollArea className="flex-1 border border-white/8 rounded-2xl bg-black/40 p-4">
                {savedPrompts.length === 0 ? (
                  <div className="size-full flex flex-col items-center justify-center text-white/30 text-xs">
                    No saved prompts found.
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {savedPrompts.map(p => (
                      <div
                        className="flex items-center justify-between border border-white/8 bg-black/20 rounded-xl p-3.5 hover:border-white/16 cursor-pointer"
                        key={p.id}
                        onClick={() => {
                          setPromptText(p.prompt)
                          setPromptStyle(p.style)
                          setActiveTab('generate')
                          showToast('Loaded prompt template')
                        }}
                      >
                        <div className="flex flex-col gap-0.5">
                          <span className="text-xs font-bold text-white leading-normal">{p.prompt}</span>
                          <span className="text-[0.625rem] text-white/40">{p.style.toUpperCase()}</span>
                        </div>
                        <IconTemplate className="text-[#8b46ff]" size="0.95rem" />
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
