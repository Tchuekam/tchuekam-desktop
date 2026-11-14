import { lazy, Suspense } from 'react'

import { ErrorBoundary } from '@/components/error-boundary'

const StandaloneShellComponent = lazy(
  // @ts-expect-error JS/JSX module without TypeScript declaration file
  () => import('./open-generative-ai/components/StandaloneShell.jsx')
)

export function ImageStudioView() {
  return (
    <div className="relative h-full w-full overflow-hidden bg-background">
      <ErrorBoundary label="image-studio">
        <Suspense
          fallback={
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
              Loading Tchuekam Studio...
            </div>
          }
        >
          <StandaloneShellComponent />
        </Suspense>
      </ErrorBoundary>
    </div>
  )
}
