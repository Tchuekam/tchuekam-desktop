import React from 'react'

export default function Link({ href, children, onClick, ...props }) {
  const handleClick = (e) => {
    if (onClick) onClick(e)
    if (e.defaultPrevented) return

    if (!href || href === '#' || href.startsWith('#')) {
      e.preventDefault()
      return
    }

    if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('mailto:')) {
      e.preventDefault()
      if (typeof window !== 'undefined' && window.hermesDesktop?.openExternal) {
        void window.hermesDesktop.openExternal(href)
      } else if (typeof window !== 'undefined') {
        window.open(href, '_blank', 'noopener,noreferrer')
      }
      return
    }

    if (href.startsWith('/studio/') || href.startsWith('/image-studio')) {
      e.preventDefault()
      const tabId = href.split('/studio/')[1] || href.split('tab=')[1]
      if (tabId && typeof window !== 'undefined') {
        const isDesktopEnv = window.location.pathname.startsWith('/image-studio')
        const targetUrl = isDesktopEnv ? `/image-studio?tab=${tabId}` : `/studio/${tabId}`
        window.history.pushState(null, '', targetUrl)
        window.dispatchEvent(new Event('popstate'))
      }
      return
    }

    if (href.startsWith('/')) {
      e.preventDefault()
    }
  }

  return (
    <a href={href} onClick={handleClick} {...props}>
      {children}
    </a>
  )
}
