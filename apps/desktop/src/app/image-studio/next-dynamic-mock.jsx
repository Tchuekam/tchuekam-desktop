import React from 'react'

export default function dynamic(importFn, options = {}) {
  const Component = React.lazy(async () => {
    const res = await importFn()
    if (res && typeof res === 'object' && res.default) {
      return res
    }
    if (typeof res === 'function' || (res && typeof res === 'object')) {
      return { default: res }
    }
    return { default: () => null }
  })
  const Loading = options.loading || (() => null)
  return function DynamicComponent(props) {
    return (
      <React.Suspense fallback={<Loading />}>
        <Component {...props} />
      </React.Suspense>
    )
  }
}
