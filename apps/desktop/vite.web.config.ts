import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import fs from 'fs/promises'
import path from 'path'
import { fileURLToPath } from 'url'
import { defineConfig, type Plugin } from 'vite'

import { rendererAliases } from './vite.aliases'

const here = path.dirname(fileURLToPath(import.meta.url))
const WEB_OUT_DIR = 'dist-web'

// Hosted web build. Same renderer as the Electron app, different shell: the
// entry installs a fetch/WebSocket bridge in place of the preload (see
// src/web/main.tsx), and `__HERMES_WEB__` flips the capability flags in
// src/lib/platform.ts.
//
// The TchuekaM backend is addressed by absolute URL (VITE_HERMES_API_URL), not
// through a same-origin /api path. Two reasons: the gateway needs a WebSocket,
// which host-level HTTP rewrites do not forward, and /api on this origin is
// already claimed by the image studio's muapi proxy below.
/**
 * Vite names the emitted HTML after its input, so the entry ships as
 * `index.web.html`. Static hosts serve `index.html` — rename it once the
 * bundle is on disk, rather than keeping a second copy of the entry in the
 * source tree where the two could drift.
 */
function emitAsIndexHtml(outDir: string): Plugin {
  return {
    name: 'tchuekam-web-index-html',
    async closeBundle() {
      const from = path.resolve(here, outDir, 'index.web.html')
      const to = path.resolve(here, outDir, 'index.html')

      await fs.rename(from, to)
    }
  }
}

export default defineConfig({
  base: '/',
  define: {
    __HERMES_WEB__: 'true'
  },
  plugins: [react(), tailwindcss(), emitAsIndexHtml(WEB_OUT_DIR)],
  build: {
    outDir: WEB_OUT_DIR,
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(here, 'index.web.html')
    }
  },
  resolve: {
    alias: rendererAliases,
    dedupe: ['react', 'react-dom']
  },
  server: {
    host: '127.0.0.1',
    port: 5175,
    strictPort: true,
    // Mirrors the desktop dev server: the image studio's bundled packages call
    // /api/* expecting the Next route handlers that proxied to muapi and
    // translated the Bearer token into muapi's x-api-key header.
    proxy: {
      '/api': {
        target: 'https://api.muapi.ai',
        changeOrigin: true,
        rewrite: (urlPath: string) => {
          if (urlPath.startsWith('/api/v1/creative-agent')) return urlPath
          if (urlPath.startsWith('/api/v1/get_upload_url')) {
            return urlPath.replace('/api/v1/get_upload_url', '/app/get_file_upload_url')
          }

          return urlPath.replace(/^\/api/, '')
        },
        configure: proxy => {
          proxy.on('proxyReq', proxyReq => {
            const auth = proxyReq.getHeader('authorization')
            if (typeof auth === 'string' && auth.startsWith('Bearer ')) {
              proxyReq.setHeader('x-api-key', auth.slice(7))
              proxyReq.removeHeader('authorization')
            }
          })
        }
      }
    }
  },
  preview: {
    host: '127.0.0.1',
    port: 4175
  }
})
