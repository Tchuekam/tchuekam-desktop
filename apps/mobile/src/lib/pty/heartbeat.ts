import { LatencyStats } from "./types";

export class HeartbeatMonitor {
  private timer: any = null;
  private pingTimestamp = 0;
  private currentLatency = 0;
  private lastHeartbeatTime = "";

  constructor(
    private intervalMs: number = 15000,
    private sendPing: () => void
  ) {}

  public start(): void {
    this.stop();
    this.timer = setInterval(() => {
      this.pingTimestamp = Date.now();
      this.sendPing();
    }, this.intervalMs);
  }

  public stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  public onPong(): LatencyStats {
    if (this.pingTimestamp > 0) {
      this.currentLatency = Date.now() - this.pingTimestamp;
    }
    this.lastHeartbeatTime = new Date().toISOString();
    return this.getStats();
  }

  public getStats(): LatencyStats {
    return {
      currentMs: this.currentLatency,
      lastHeartbeat: this.lastHeartbeatTime,
    };
  }
}
