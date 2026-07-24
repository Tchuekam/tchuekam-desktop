/**
 * TchueKAM Mobile — Centralized Error Hierarchy
 */

export class AppError extends Error {
  public readonly code: string;
  public readonly details?: any;
  public readonly recoverable: boolean;
  public readonly timestamp: string;

  constructor(message: string, code = "INTERNAL_ERROR", details?: any, recoverable = true) {
    super(message);
    this.name = this.constructor.name;
    this.code = code;
    this.details = details;
    this.recoverable = recoverable;
    this.timestamp = new Date().toISOString();
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class ApiError extends AppError {
  public readonly status?: number;

  constructor(message: string, status?: number, code = "API_ERROR", details?: any) {
    super(message, code, details, status ? status < 500 : true);
    this.status = status;
  }
}

export class AuthenticationError extends AppError {
  constructor(message = "Authentication credentials invalid or expired", details?: any) {
    super(message, "AUTH_UNAUTHORIZED", details, false);
  }
}

export class NetworkError extends AppError {
  constructor(message = "Network connection failed", details?: any) {
    super(message, "NETWORK_DISCONNECTED", details, true);
  }
}

export class TimeoutError extends AppError {
  constructor(message = "Request timed out", details?: any) {
    super(message, "REQUEST_TIMEOUT", details, true);
  }
}

export class ValidationError extends AppError {
  constructor(message = "Payload validation failed", details?: any) {
    super(message, "VALIDATION_FAILED", details, false);
  }
}

export class WebSocketError extends AppError {
  constructor(message = "WebSocket error occurred", details?: any) {
    super(message, "WEBSOCKET_ERROR", details, true);
  }
}

export class PTYError extends AppError {
  constructor(message = "PTY Engine error", details?: any) {
    super(message, "PTY_ENGINE_ERROR", details, true);
  }
}
