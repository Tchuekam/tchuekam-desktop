'use client';

import { useState } from 'react';

export default function ApiKeyModal({
  onSave,
  onClose,
  overlay = false,
  title,
  subtitle,
  initialKey = '',
  initialProvider = 'fal',
  authState = 'unconfigured',
  errorMessage = '',
  isValidating = false,
}) {
  const [selectedProvider, setSelectedProvider] = useState(initialProvider);
  const [falKey, setFalKey] = useState(initialProvider === 'fal' ? initialKey : '');
  const [muapiKey, setMuapiKey] = useState(initialProvider === 'muapi' ? initialKey : '');
  const [localError, setLocalError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const activeKey = selectedProvider === 'fal' ? falKey : muapiKey;
  const setActiveKey = (val) => {
    if (selectedProvider === 'fal') setFalKey(val);
    else setMuapiKey(val);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = activeKey.trim();
    if (!trimmed) {
      setLocalError(`Please enter your ${selectedProvider === 'fal' ? 'FAL.ai' : 'MuAPI'} API key.`);
      return;
    }
    if (trimmed === 'genimage_free_key') {
      setLocalError('The demo placeholder key is not supported. Please provide a valid production API key.');
      return;
    }

    setSubmitting(true);
    setLocalError('');
    try {
      await onSave(trimmed, selectedProvider);
    } catch (err) {
      setLocalError(err?.message || 'Failed to validate and save API key.');
    } finally {
      setSubmitting(false);
    }
  };

  const displayError = localError || errorMessage;
  const loading = isValidating || submitting;

  const wrapperClass = overlay
    ? 'fixed inset-0 z-[200] bg-black/75 backdrop-blur-md flex items-center justify-center px-4 font-sans animate-fade-in-up'
    : 'min-h-screen bg-background flex items-center justify-center px-4 font-sans';

  return (
    <div className={wrapperClass}>
      <div className="w-full max-w-md bg-card/95 backdrop-blur-xl border border-border rounded-2xl p-7 shadow-2xl relative text-foreground">
        {overlay && onClose && authState === 'authenticated' && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute top-4 right-4 w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center justify-center"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        )}

        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center border border-primary/20 mb-3.5 group">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className="text-primary">
              <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L12 17.25l-4.5-4.5L15.5 7.5z" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <h1 className="text-xl font-bold tracking-tight mb-1 text-foreground">
            {title || 'TchueKAM Creative Studio'}
          </h1>
          <p className="text-muted-foreground text-xs leading-relaxed max-w-xs">
            {subtitle || 'Select an AI provider and enter your API credentials to begin creating.'}
          </p>
        </div>

        {/* Provider Switcher Tabs */}
        <div className="flex rounded-xl bg-muted/60 p-1 mb-5 border border-border">
          <button
            type="button"
            onClick={() => { setSelectedProvider('fal'); setLocalError(''); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              selectedProvider === 'fal'
                ? 'bg-card text-foreground shadow-sm border border-border font-bold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <span>FAL.ai</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 font-mono">Primary</span>
          </button>
          <button
            type="button"
            onClick={() => { setSelectedProvider('muapi'); setLocalError(''); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              selectedProvider === 'muapi'
                ? 'bg-card text-foreground shadow-sm border border-border font-bold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <span>MuAPI</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-mono">Optional</span>
          </button>
        </div>

        {/* Auth State Guidance Banner */}
        {authState === 'invalid' && (
          <div className="mb-4 p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs leading-relaxed">
            <div className="font-semibold mb-0.5">Authentication Failed</div>
            <div>{displayError || 'The API key was rejected. Please check your credentials.'}</div>
          </div>
        )}

        {authState === 'insufficient_quota' && (
          <div className="mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-500 text-xs leading-relaxed">
            <div className="font-semibold mb-0.5">Quota Limit Reached</div>
            <div>{displayError || 'Account balance depleted or quota limit reached.'}</div>
          </div>
        )}

        {authState === 'unavailable' && (
          <div className="mb-4 p-3 rounded-xl bg-muted border border-border text-muted-foreground text-xs leading-relaxed">
            <div className="font-semibold mb-0.5">Provider Unavailable</div>
            <div>{displayError || 'Unable to connect to the authentication provider.'}</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-foreground">
                {selectedProvider === 'fal' ? 'FAL.ai Key (FAL_KEY)' : 'MuAPI Key (MUAPI_KEY)'}
              </label>
              <a
                href={selectedProvider === 'fal' ? 'https://fal.ai/dashboard/keys' : 'https://muapi.ai'}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] text-primary hover:underline font-medium"
              >
                Get Key &rarr;
              </a>
            </div>
            <input
              type="password"
              value={activeKey}
              onChange={(e) => setActiveKey(e.target.value)}
              placeholder={selectedProvider === 'fal' ? 'Enter your FAL.ai key...' : 'Enter your MuAPI key...'}
              disabled={loading}
              className="w-full bg-muted/50 border border-border rounded-xl px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary font-mono transition-all disabled:opacity-50"
              autoFocus
            />
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              {selectedProvider === 'fal'
                ? 'Primary engine powering FLUX 2, Nano Banana Pro, Veo 3.1, and LTX video.'
                : 'Provides access to specialized community models and workflow nodes.'}
            </p>
          </div>

          {displayError && authState !== 'invalid' && authState !== 'insufficient_quota' && authState !== 'unavailable' && (
            <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs">
              {displayError}
            </div>
          )}

          <div className="flex gap-2 pt-2">
            {overlay && onClose && (
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="flex-1 py-2.5 rounded-xl border border-border bg-muted/50 hover:bg-muted text-xs font-semibold text-foreground transition-all cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>
            )}
            <button
              type="submit"
              disabled={loading}
              className="flex-1 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {loading ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  <span>Validating...</span>
                </>
              ) : (
                <span>Save Credentials</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
