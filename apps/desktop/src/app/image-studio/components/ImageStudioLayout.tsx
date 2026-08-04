/**
 * TchueKAM Image Studio — Open Generative AI Integration
 */

import React, { useEffect, useRef } from 'react'

export function ImageStudioView() {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const app = containerRef.current
    if (!app) return
    app.innerHTML = ''

    let mountedPages: Record<string, HTMLElement> = {}

    // Import Header & ImageStudio from Open-Generative-AI
    Promise.all([
      // @ts-ignore
      import('../open-generative-ai/src/components/Header.js'),
      // @ts-ignore
      import('../open-generative-ai/src/components/ImageStudio.js')
    ]).then(([{ Header }, { ImageStudio }]) => {
      if (!app) return

      const contentArea = document.createElement('main')
      contentArea.id = 'content-area'
      contentArea.className = 'flex-1 relative w-full overflow-hidden flex flex-col bg-[#050505]'

      function navigate(page: string) {
        Object.values(mountedPages).forEach(node => {
          node.style.display = 'none'
        })

        if (mountedPages[page]) {
          mountedPages[page].style.display = ''
        } else {
          const wrapper = document.createElement('div')
          wrapper.style.cssText = 'width:100%;height:100%;display:flex;flex-direction:column;'
          contentArea.appendChild(wrapper)
          mountedPages[page] = wrapper

          if (page === 'image') {
            wrapper.appendChild(ImageStudio())
          } else if (page === 'video') {
            // @ts-ignore
            import('../open-generative-ai/src/components/VideoStudio.js').then(({ VideoStudio }) => {
              wrapper.appendChild(VideoStudio())
            })
          } else if (page === 'cinema') {
            // @ts-ignore
            import('../open-generative-ai/src/components/CinemaStudio.js').then(({ CinemaStudio }) => {
              wrapper.appendChild(CinemaStudio())
            })
          } else if (page === 'lipsync') {
            // @ts-ignore
            import('../open-generative-ai/src/components/LipSyncStudio.js').then(({ LipSyncStudio }) => {
              wrapper.appendChild(LipSyncStudio())
            })
          } else if (page === 'workflows') {
            // @ts-ignore
            import('../open-generative-ai/src/components/WorkflowStudio.js').then(({ WorkflowStudio }) => {
              wrapper.appendChild(WorkflowStudio())
            })
          } else if (page === 'agents') {
            // @ts-ignore
            import('../open-generative-ai/src/components/AgentStudio.js').then(({ AgentStudio }) => {
              wrapper.appendChild(AgentStudio())
            })
          } else if (page === 'mcp-cli') {
            // @ts-ignore
            import('../open-generative-ai/src/components/McpCliStudio.js').then(({ McpCliStudio }) => {
              wrapper.appendChild(McpCliStudio())
            })
          }
        }
      }

      app.appendChild(Header(navigate))
      app.appendChild(contentArea)

      window.addEventListener('navigate', (e: any) => {
        if (e.detail?.page === 'settings') {
          // @ts-ignore
          import('../open-generative-ai/src/components/SettingsModal.js').then(({ SettingsModal }) => {
            document.body.appendChild(SettingsModal())
          })
        } else if (e.detail?.page) {
          navigate(e.detail.page)
        }
      })

      navigate('image')
    }).catch(err => {
      console.error('Failed to load Open Generative AI modules:', err)
    })

    return () => {
      if (app) app.innerHTML = ''
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[#050505] pt-(--titlebar-height) text-white"
    />
  )
}
