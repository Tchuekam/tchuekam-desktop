import { IconDeviceMobile, IconDownload, IconSparkles, IconX } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { triggerHaptic } from '@/lib/haptics'
import { MOBILE_ROUTE } from '../routes'

const DISMISSED_KEY = 'tchuekam_mobile_banner_dismissed_v1'

export function MobilePromoBanner() {
  const [visible, setVisible] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    // If user is already on /mobile or dismissed it, do not show
    if (location.pathname === MOBILE_ROUTE) {
      setVisible(false)
      return
    }

    try {
      const dismissed = sessionStorage.getItem(DISMISSED_KEY)
      if (dismissed === 'true') {
        setVisible(false)
        return
      }
    } catch {
      // Ignore storage errors in sandboxed contexts
    }

    // Show for all web visitors or mobile browsers
    const isMobileDevice =
      typeof window !== 'undefined' &&
      (window.innerWidth <= 840 || /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent))

    setVisible(isMobileDevice)
  }, [location.pathname])

  if (!visible) return null

  const handleDismiss = () => {
    triggerHaptic('tap')
    setVisible(false)
    try {
      sessionStorage.setItem(DISMISSED_KEY, 'true')
    } catch {
      // Ignore
    }
  }

  const handleDownload = () => {
    triggerHaptic('success')
    const link = document.createElement('a')
    link.href = '/api/download/android'
    link.setAttribute('download', 'TchueKAM-Mobile.apk')
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const handleOpenMobile = () => {
    triggerHaptic('tap')
    navigate(MOBILE_ROUTE)
  }

  return (
    <div className="relative z-60 flex w-full items-center justify-between gap-3 border-b border-cyan-500/25 bg-linear-to-r from-cyan-950/80 via-neutral-900/95 to-slate-950/90 px-4 py-2 text-xs text-white shadow-md backdrop-blur-md">
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="grid size-6 shrink-0 place-items-center rounded-md bg-cyan-500/20 text-cyan-400">
          <IconDeviceMobile className="size-3.5" />
        </div>
        <div className="truncate">
          <span className="font-semibold text-cyan-300">TchueKAM Mobile is out!</span>{' '}
          <span className="hidden sm:inline text-neutral-300">
            Download the Android APK in one click or install instantly on iOS.
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          onClick={handleDownload}
          className="flex cursor-pointer items-center gap-1.5 rounded-md bg-cyan-400 px-2.5 py-1 text-[0.7rem] font-bold text-slate-950 shadow-sm transition hover:bg-cyan-300 active:scale-95"
        >
          <IconDownload className="size-3" />
          <span>Download APK</span>
        </button>

        <Button
          variant="outline"
          size="sm"
          onClick={handleOpenMobile}
          className="h-6 gap-1 border-white/20 bg-white/5 px-2 text-[0.7rem] text-white hover:bg-white/10"
        >
          <IconSparkles className="size-3 text-cyan-400" />
          <span className="hidden xs:inline">Try App</span>
        </Button>

        <button
          type="button"
          aria-label="Dismiss banner"
          onClick={handleDismiss}
          className="grid size-5 cursor-pointer place-items-center rounded-sm text-neutral-400 hover:bg-white/10 hover:text-white"
        >
          <IconX className="size-3.5" />
        </button>
      </div>
    </div>
  )
}

