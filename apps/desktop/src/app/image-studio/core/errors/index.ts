/**
 * TchueKAM Image Studio v2 — Structured Error Classes
 */

export interface ErrorDetails {
  code: string
  message: string
  provider?: string
  reason?: string
  recoverySuggestion?: string
  cause?: unknown
}

export class StudioError extends Error {
  public readonly code: string
  public readonly provider?: string
  public readonly reason?: string
  public readonly recoverySuggestion?: string

  constructor(details: ErrorDetails) {
    super(details.message)
    this.name = 'StudioError'
    this.code = details.code
    this.provider = details.provider
    this.reason = details.reason || details.message
    this.recoverySuggestion =
      details.recoverySuggestion || 'Please verify your network connection and API configuration.'
  }
}

export class ProviderError extends StudioError {
  constructor(message: string, provider: string, recoverySuggestion?: string) {
    super({
      code: 'PROVIDER_ERROR',
      message,
      provider,
      reason: `AI Provider (${provider}) failed to process request.`,
      recoverySuggestion: recoverySuggestion || 'Try selecting a different AI provider in settings.'
    })
    this.name = 'ProviderError'
  }
}

export class CanvasError extends StudioError {
  constructor(message: string, reason?: string) {
    super({
      code: 'CANVAS_ERROR',
      message,
      reason: reason || 'Canvas operation failed',
      recoverySuggestion: 'Ensure valid layer bounds and canvas state.'
    })
    this.name = 'CanvasError'
  }
}

export class ValidationError extends StudioError {
  constructor(message: string) {
    super({
      code: 'VALIDATION_ERROR',
      message,
      reason: 'Invalid parameters or missing required inputs',
      recoverySuggestion: 'Check parameter inputs and try again.'
    })
    this.name = 'ValidationError'
  }
}

export class ProjectError extends StudioError {
  constructor(message: string, reason?: string) {
    super({
      code: 'PROJECT_ERROR',
      message,
      reason: reason || 'Project operation failed',
      recoverySuggestion: 'Verify disk access and project structure.'
    })
    this.name = 'ProjectError'
  }
}
