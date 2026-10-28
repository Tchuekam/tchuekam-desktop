import path from 'path'
import { fileURLToPath } from 'url'

// Shared by vite.config.ts (Electron renderer) and vite.web.config.ts (hosted
// web build). Both bundle the same source tree, so an alias added for one and
// not the other resolves in development and fails at build time in the other.
const here = path.dirname(fileURLToPath(import.meta.url))

export const rendererAliases = {
  '@': path.resolve(here, './src'),
  '@hermes/shared': path.resolve(here, '../shared/src'),
  studio: path.resolve(here, './src/app/image-studio/open-generative-ai/packages/studio/src/index.js'),
  'workflow-builder': path.resolve(
    here,
    './src/app/image-studio/open-generative-ai/packages/Vibe-Workflow/packages/workflow-builder/src/index.js'
  ),
  'ai-agent': path.resolve(
    here,
    './src/app/image-studio/open-generative-ai/packages/Open-Poe-AI/packages/agents/src/index.js'
  ),
  'design-agent': path.resolve(
    here,
    './src/app/image-studio/open-generative-ai/packages/Open-AI-Design-Agent/packages/design-agent/src/index.js'
  ),
  'next/navigation': path.resolve(here, './src/app/image-studio/next-navigation-mock.jsx'),
  'next/link': path.resolve(here, './src/app/image-studio/next-link-mock.jsx'),
  'next/image': path.resolve(here, './src/app/image-studio/next-image-mock.jsx'),
  'next/router': path.resolve(here, './src/app/image-studio/next-navigation-mock.jsx'),
  'next/dynamic': path.resolve(here, './src/app/image-studio/next-dynamic-mock.jsx'),
  react: path.resolve(here, '../../node_modules/react'),
  'react-dom': path.resolve(here, '../../node_modules/react-dom'),
  'react/jsx-dev-runtime': path.resolve(here, '../../node_modules/react/jsx-dev-runtime.js'),
  'react/jsx-runtime': path.resolve(here, '../../node_modules/react/jsx-runtime.js')
}
