import React, { Component } from 'react';

/**
 * Robust error boundary for dynamically loaded studio tabs.
 * Recovers gracefully from chunk load failures and rendering errors
 * without crashing or reloading the entire application.
 */
export class StudioErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error(`[StudioErrorBoundary] Error in ${this.props.studioName || 'Studio'}:`, error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const isChunkError = this.state.error?.message?.includes('dynamically imported module') ||
        this.state.error?.message?.includes('Loading chunk');

      return (
        <div className="h-full w-full bg-[#0d0d0e] flex flex-col items-center justify-center p-6 text-center select-none">
          <div className="max-w-md w-full bg-[#18181b] border border-white/10 rounded-2xl p-6 shadow-2xl flex flex-col items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>

            <div className="flex flex-col gap-1">
              <h3 className="text-white text-base font-semibold">
                {isChunkError ? 'Failed to Load Studio Module' : `${this.props.studioName || 'Studio'} Encountered an Error`}
              </h3>
              <p className="text-white/50 text-xs leading-relaxed">
                {isChunkError
                  ? 'A network interruption prevented loading this studio module. Please retry your connection.'
                  : (this.state.error?.message || 'An unexpected error occurred while rendering this module.')}
              </p>
            </div>

            <div className="flex items-center gap-3 mt-2">
              <button
                type="button"
                onClick={this.handleRetry}
                className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-semibold transition-all border border-white/10 hover:border-white/20"
              >
                Retry Module
              </button>
              {this.props.onResetTab && (
                <button
                  type="button"
                  onClick={this.props.onResetTab}
                  className="px-4 py-2 rounded-xl bg-primary/20 hover:bg-primary/30 text-primary text-xs font-semibold transition-all border border-primary/30"
                >
                  Return to Image Studio
                </button>
              )}
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export function StudioLoadingFallback({ name = 'Studio' }) {
  return (
    <div className="h-full w-full bg-[#0d0d0e] flex flex-col items-center justify-center text-white/40 gap-3 select-none">
      <div className="w-7 h-7 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      <span className="text-xs font-medium tracking-wide">Loading {name}...</span>
    </div>
  );
}

export default StudioErrorBoundary;
