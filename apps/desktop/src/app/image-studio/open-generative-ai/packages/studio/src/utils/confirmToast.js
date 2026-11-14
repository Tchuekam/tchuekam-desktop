import React from 'react';
import toast from 'react-hot-toast';

/**
 * Display a Tchuekam-native, non-blocking confirmation dialog using react-hot-toast.
 * Replaces synchronous window.confirm() to prevent blocking the Electron renderer thread.
 */
export function confirmToast(message, onConfirm, { title = 'Confirm Action', confirmLabel = 'Delete', cancelLabel = 'Cancel' } = {}) {
  toast((t) => (
    React.createElement('div', { className: 'flex flex-col gap-2 p-1 min-w-[220px]' },
      React.createElement('div', { className: 'text-xs font-semibold text-white/90' }, message || title),
      React.createElement('div', { className: 'flex justify-end gap-2 mt-1' },
        React.createElement('button', {
          type: 'button',
          onClick: () => toast.dismiss(t.id),
          className: 'px-2.5 py-1 text-[11px] rounded bg-white/10 hover:bg-white/20 text-white/70 hover:text-white transition-colors font-medium'
        }, cancelLabel),
        React.createElement('button', {
          type: 'button',
          onClick: () => {
            toast.dismiss(t.id);
            onConfirm();
          },
          className: 'px-2.5 py-1 text-[11px] rounded bg-red-600 hover:bg-red-500 text-white font-semibold transition-colors'
        }, confirmLabel)
      )
    )
  ), {
    duration: 6000,
    style: {
      background: '#18181b',
      color: '#ffffff',
      border: '1px solid rgba(255, 255, 255, 0.15)',
      borderRadius: '12px',
      boxShadow: '0 10px 30px rgba(0, 0, 0, 0.6)',
      padding: '12px 14px',
    },
  });
}

export default confirmToast;
