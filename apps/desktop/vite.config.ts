import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  build: {
    // Keep desktop packaging stable: Shiki ships many dynamic chunks by
    // default, and electron-builder can OOM scanning thousands of files.
    rolldownOptions: {
      output: {
        codeSplitting: false
      }
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@hermes/shared': path.resolve(__dirname, '../shared/src'),
      studio: path.resolve(__dirname, './src/app/image-studio/open-generative-ai/packages/studio/src/index.js'),
      'workflow-builder': path.resolve(__dirname, './src/app/image-studio/open-generative-ai/packages/Vibe-Workflow/packages/workflow-builder/src/index.js'),
      'ai-agent': path.resolve(__dirname, './src/app/image-studio/open-generative-ai/packages/Open-Poe-AI/packages/agents/src/index.js'),
      'design-agent': path.resolve(__dirname, './src/app/image-studio/open-generative-ai/packages/Open-AI-Design-Agent/packages/design-agent/src/index.js'),
      'next/navigation': path.resolve(__dirname, './src/app/image-studio/next-navigation-mock.jsx'),
      'next/link': path.resolve(__dirname, './src/app/image-studio/next-link-mock.jsx'),
      'next/image': path.resolve(__dirname, './src/app/image-studio/next-image-mock.jsx'),
      'next/router': path.resolve(__dirname, './src/app/image-studio/next-navigation-mock.jsx'),
      'next/dynamic': path.resolve(__dirname, './src/app/image-studio/next-dynamic-mock.jsx'),
      react: path.resolve(__dirname, '../../node_modules/react'),
      'react-dom': path.resolve(__dirname, '../../node_modules/react-dom'),
      'react/jsx-dev-runtime': path.resolve(__dirname, '../../node_modules/react/jsx-dev-runtime.js'),
      'react/jsx-runtime': path.resolve(__dirname, '../../node_modules/react/jsx-runtime.js')
    },
    dedupe: ['react', 'react-dom']
  },
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    // The studio packages were written against the Next app, where /api/* route
    // handlers re-issue calls to api.muapi.ai server-side (dodging CORS) and
    // translate the Bearer token into muapi's x-api-key header. The packaged
    // desktop app runs on file:// and calls upstream directly, but the dev
    // server is http:// — so without this proxy every studio API call 404s
    // during development. Mirrors the mapping in
    // src/app/image-studio/open-generative-ai/app/api/**/route.js.
    proxy: {
      '/api': {
        target: 'https://api.muapi.ai',
        changeOrigin: true,
        rewrite: (urlPath: string) => {
          // app/api/v1/creative-agent/[[...path]] forwards to the same path.
          if (urlPath.startsWith('/api/v1/creative-agent')) return urlPath
          // app/api/v1/get_upload_url forwards to /app/get_file_upload_url.
          if (urlPath.startsWith('/api/v1/get_upload_url')) {
            return urlPath.replace('/api/v1/get_upload_url', '/app/get_file_upload_url')
          }
          // The rest (/api/api/v1/*, /api/agents/*, /api/app/*, /api/workflow/*)
          // drop the mount prefix.
          return urlPath.replace(/^\/api/, '')
        },
        configure: (proxy) => {
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
    port: 4174
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    // Several component tests render UI that awaits mocked config endpoints via
    // `waitFor`. Each takes ~6-8s; under the full parallel suite, CPU contention
    // pushes them past vitest's 5s default, causing flaky timeouts. Give async
    // assertions headroom so the suite is deterministic.
    testTimeout: 20000,
    hookTimeout: 20000,
    // Vitest covers the renderer (src/**). Exclude build artifacts, packaged
    // release output, and bundled native-dep tests — and the electron/*.test.cjs
    // suites, which run under Node's built-in test runner (`node --test`), not
    // vitest. Without this, vitest globs thousands of stray *.test.js files.
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/build/**',
      '**/release/**',
      'electron/**',
      'src/app/image-studio/open-generative-ai/tests/**',
      '**/.{idea,git,cache,output,temp}/**'
    ]
  }
})
