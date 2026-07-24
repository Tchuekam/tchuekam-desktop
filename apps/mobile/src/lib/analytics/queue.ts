import { ANALYTICS_CONFIG } from "./config";
import { PrivacyManager } from "./privacy";

export interface AnalyticsEvent {
  event: string;
  properties: Record<string, any>;
  timestamp: string;
}

export class AnalyticsEventQueue {
  private queue: AnalyticsEvent[] = [];
  private timer: any = null;

  constructor() {
    this.startFlushing();
  }

  public enqueue(event: string, properties: Record<string, any> = {}): void {
    if (!PrivacyManager.isTelemetryEnabled()) {
      return;
    }

    this.queue.push({
      event,
      properties: {
        client: "tchuekam_mobile_native",
        platform: "mobile",
        ...properties,
      },
      timestamp: new Date().toISOString(),
    });

    if (this.queue.length >= ANALYTICS_CONFIG.batchSize) {
      this.flush();
    }
  }

  public async flush(): Promise<void> {
    if (this.queue.length === 0 || !PrivacyManager.isTelemetryEnabled()) {
      return;
    }

    const batch = [...this.queue];
    this.queue = [];

    try {
      await Promise.all(
        batch.map((item) =>
          fetch(`${ANALYTICS_CONFIG.host}/capture/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              api_key: ANALYTICS_CONFIG.key,
              event: item.event,
              properties: {
                distinct_id: "mobile_user_native",
                ...item.properties,
              },
              timestamp: item.timestamp,
            }),
          }).catch(() => {})
        )
      );
    } catch (err) {
      console.warn("Analytics flush failed:", err);
    }
  }

  private startFlushing(): void {
    if (!this.timer) {
      this.timer = setInterval(() => this.flush(), ANALYTICS_CONFIG.flushIntervalMs);
    }
  }
}

export const analyticsQueue = new AnalyticsEventQueue();
