export class ReconnectManager {
  private attempts = 0;
  private timer: any = null;

  constructor(
    private maxAttempts = 10,
    private initialDelayMs = 1000,
    private maxDelayMs = 30000
  ) {}

  public scheduleReconnect(reconnectFn: () => void): boolean {
    if (this.attempts >= this.maxAttempts) {
      console.warn("Max reconnect attempts reached (" + this.maxAttempts + ")");
      return false;
    }

    this.attempts++;
    const delay = Math.min(this.initialDelayMs * Math.pow(2, this.attempts - 1), this.maxDelayMs);

    this.clear();
    this.timer = setTimeout(() => {
      reconnectFn();
    }, delay);

    return true;
  }

  public reset(): void {
    this.attempts = 0;
    this.clear();
  }

  public clear(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  public getAttemptCount(): number {
    return this.attempts;
  }
}
