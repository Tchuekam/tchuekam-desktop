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
    strictPort: true
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
      '**/.{idea,git,cache,output,temp}/**'
    ]
  }
})
