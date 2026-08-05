import { Suspense, lazy } from 'react'

const StandaloneShellComponent = lazy(
  // @ts-expect-error JS/JSX module without TypeScript declaration file
  () => import('./open-generative-ai/components/StandaloneShell.jsx')
)

export function ImageStudioView() {
  return (
    <div className="relative h-full w-full overflow-hidden bg-background">
      <Suspense
        fallback={
          <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
            Loading Tchuekam Studio...
          </div>
        }
      >
        <StandaloneShellComponent />
      </Suspense>
    </div>
  )
}
