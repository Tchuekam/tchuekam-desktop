import React from 'react'

// Next's <Image> optimizes/serves images through the Next server, which does not
// exist in the desktop shell. Render a plain <img> and translate the layout props
// we actually use, dropping the loader-only ones so React doesn't forward unknown
// attributes to the DOM.
export default function Image({
  src,
  alt = '',
  width,
  height,
  fill,
  style,
  // Next-only props — intentionally discarded.
  priority,
  quality,
  placeholder,
  blurDataURL,
  unoptimized,
  loader,
  onLoadingComplete,
  ...props
}) {
  // `fill` makes the image cover its nearest positioned ancestor. object-fit is
  // supplied by the caller's className (e.g. "object-cover"), so don't set it here.
  const resolvedStyle = fill
    ? { position: 'absolute', inset: 0, width: '100%', height: '100%', ...style }
    : style

  const resolvedSrc = typeof src === 'object' && src !== null ? src.src || src.default || '' : src

  return (
    <img
      src={resolvedSrc}
      alt={alt}
      width={fill ? undefined : width}
      height={fill ? undefined : height}
      style={resolvedStyle}
      onLoad={onLoadingComplete}
      {...props}
    />
  )
}
