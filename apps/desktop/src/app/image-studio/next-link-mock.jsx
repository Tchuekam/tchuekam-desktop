import React from 'react'

import { navigate, openExternal } from './next-navigation-mock'

// Shares its URL translation with the navigation mock so a <Link> and a
// router.push() to the same href always land on the same desktop route.
export default function Link({ href, children, onClick, ...props }) {
  const handleClick = e => {
    if (onClick) {
      onClick(e)
    }

    if (e.defaultPrevented) {
      return
    }

    // In-page anchors keep their default behaviour.
    if (!href || href === '#' || href.startsWith('#')) {
      e.preventDefault()

      return
    }

    if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('mailto:')) {
      e.preventDefault()
      openExternal(href)

      return
    }

    // Everything else is in-app: the desktop shell only renders /image-studio,
    // so translate rather than letting the browser follow a dead route.
    e.preventDefault()
    navigate(href, 'push')
  }

  return (
    <a href={href} onClick={handleClick} {...props}>
      {children}
    </a>
  )
}
