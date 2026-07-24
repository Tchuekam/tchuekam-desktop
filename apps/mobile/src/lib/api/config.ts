/**
 * API Configuration with Automatic Endpoint Failover
 */

export const API_CONFIG = {
  primaryBaseUrl: "https://agent.tchuekam.com/api",
  fallbackBaseUrl: "https://tchuekam-backend-production.up.railway.app/api",
  wsBaseUrl: "wss://agent.tchuekam.com/api/pty",
  timeoutMs: 15000,
  maxRetries: 3,
  retryDelayMs: 1000,
} as const;

export class EndpointResolver {
  private static activeBaseUrl: string = API_CONFIG.primaryBaseUrl;

  public static getBaseUrl(): string {
    return this.activeBaseUrl;
  }

  public static markPrimaryFailed(): void {
    if (this.activeBaseUrl === API_CONFIG.primaryBaseUrl) {
      console.warn("Primary API endpoint unavailable. Switching to Railway fallback endpoint.");
      this.activeBaseUrl = API_CONFIG.fallbackBaseUrl;
    }
  }

  public static resetToPrimary(): void {
    this.activeBaseUrl = API_CONFIG.primaryBaseUrl;
  }
}
