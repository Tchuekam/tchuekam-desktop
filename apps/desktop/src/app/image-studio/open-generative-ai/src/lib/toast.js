/**
 * Lightweight DOM toast notification for vanilla JS components.
 * Replaces window.alert() without external dependencies.
 */
export function showToast(message, type = 'info') {
  if (typeof document === 'undefined') return;
  let container = document.getElementById('og-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'og-toast-container';
    container.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:99999;display:flex;flex-direction:column;gap:0.5rem;pointer-events:none;max-width:380px;';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const isError = type === 'error';
  toast.style.cssText = `pointer-events:auto;padding:10px 16px;border-radius:10px;font-size:12px;font-weight:600;box-shadow:0 10px 25px rgba(0,0,0,0.5);transition:all 0.25s ease;background:#18181b;color:${isError ? '#f87171' : '#ffffff'};border:1px solid ${isError ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.12)'};`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-8px)';
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

/**
 * Non-blocking accessible confirmation dialog for vanilla JS components.
 * Replaces window.confirm().
 */
export function showConfirm(message, onConfirm, onCancel) {
  if (typeof document === 'undefined') return;
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);backdrop-filter:blur(4px);z-index:999999;display:flex;align-items:center;justify-content:center;padding:16px;animation:fadeIn 0.15s ease-out;';

  const modal = document.createElement('div');
  modal.style.cssText = 'background:#18181b;border:1px solid rgba(255,255,255,0.12);border-radius:12px;padding:20px;max-width:400px;width:100%;box-shadow:0 20px 40px rgba(0,0,0,0.6);display:flex;flex-direction:column;gap:16px;';

  const msgEl = document.createElement('p');
  msgEl.style.cssText = 'margin:0;font-size:14px;color:#e4e4e7;line-height:1.5;font-weight:500;';
  msgEl.textContent = message;
  modal.appendChild(msgEl);

  const btnRow = document.createElement('div');
  btnRow.style.cssText = 'display:flex;justify-content:flex-end;gap:10px;';

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.style.cssText = 'padding:8px 14px;font-size:12px;font-weight:600;color:#a1a1aa;background:transparent;border:1px solid rgba(255,255,255,0.15);border-radius:6px;cursor:pointer;';
  cancelBtn.onmouseenter = () => cancelBtn.style.background = 'rgba(255,255,255,0.05)';
  cancelBtn.onmouseleave = () => cancelBtn.style.background = 'transparent';
  cancelBtn.onclick = () => {
    overlay.remove();
    if (onCancel) onCancel();
  };

  const confirmBtn = document.createElement('button');
  confirmBtn.type = 'button';
  confirmBtn.textContent = 'Confirm';
  confirmBtn.style.cssText = 'padding:8px 14px;font-size:12px;font-weight:600;color:#ffffff;background:#dc2626;border:none;border-radius:6px;cursor:pointer;';
  confirmBtn.onmouseenter = () => confirmBtn.style.background = '#ef4444';
  confirmBtn.onmouseleave = () => confirmBtn.style.background = '#dc2626';
  confirmBtn.onclick = () => {
    overlay.remove();
    if (onConfirm) onConfirm();
  };

  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(confirmBtn);
  modal.appendChild(btnRow);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

export default showToast;
