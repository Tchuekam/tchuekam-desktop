/**
 * TchueKAM Image Studio v2 — Toast Alert Component
 */

import { IconAlertCircle, IconCheck } from '@tabler/icons-react'
import { useStore } from '@nanostores/react'
import React from 'react'
import { cn } from '@/lib/utils'
import { $toastMessage } from '../stores/ui.store'

export const ToastAlert: React.FC = () => {
  const toast = useStore($toastMessage)

  if (!toast) return null

  return (
    <div
      className={cn(
        'absolute top-16 right-6 z-50 flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold shadow-lg backdrop-blur-md transition-all duration-200',
        toast.type === 'success' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : '',
        toast.type === 'error' ? 'bg-red-500/20 text-red-400 border border-red-500/30' : '',
        toast.type === 'info' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : ''
      )}
    >
      {toast.type === 'error' ? <IconAlertCircle size="1.2rem" /> : <IconCheck size="1.2rem" />}
      <span>{toast.message}</span>
    </div>
  )
}
