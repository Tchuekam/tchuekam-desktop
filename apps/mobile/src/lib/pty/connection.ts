import { API_CONFIG } from "../api/config";
import { AuthService } from "../api/auth";
import { ConnectionStatus, LatencyStats, PtyFrame, PtyConnectionOptions } from "./types";
import { PtyProtocol } from "./protocol";
import { HeartbeatMonitor } from "./heartbeat";
import { ReconnectManager } from "./reconnect";
import { PendingFrameQueue } from "./queue";
import { PtyEventEmitter } from "./events";

export class PtyConnectionManager {
  private static instance: PtyConnectionManager | null = null;

  private ws: WebSocket | null = null;
  private status: ConnectionStatus = "disconnected";
  private emitter = new PtyEventEmitter();
  private heartbeat: HeartbeatMonitor;
  private reconnector = new ReconnectManager();
  private queue = new PendingFrameQueue();
  private currentSessionId: string | null = null;

  private constructor() {
    this.heartbeat = new HeartbeatMonitor(15000, () => {
      this.sendFrame({ type: "ping", payload: "heartbeat" });
    });
  }

  public static getInstance(): PtyConnectionManager {
    if (!PtyConnectionManager.instance) {
      PtyConnectionManager.instance = new PtyConnectionManager();
    }
    return PtyConnectionManager.instance;
  }

  public async connect(sessionId?: string): Promise<void> {
    if (this.status === "connected" || this.status === "connecting") {
      return;
    }

    this.setStatus("connecting");
    if (sessionId) {
      this.currentSessionId = sessionId;
    }

    try {
      const token = await AuthService.getSessionToken();
      const wsUrl = `${API_CONFIG.wsBaseUrl}${token ? `?token=${encodeURIComponent(token)}` : ""}`;

      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.setStatus("connected");
        this.reconnector.reset();
        this.heartbeat.start();
        this.queue.flush((frame) => this.sendFrame(frame));
      };

      this.ws.onmessage = (event) => {
        const frame = PtyProtocol.deserialize(event.data);

        if (frame.type === "pong") {
          const stats = this.heartbeat.onPong();
          this.emitter.emit("latency", stats);
          return;
        }

        this.emitter.emit("message", frame);
        this.emitter.emit("output", frame.payload);
      };

      this.ws.onerror = (err) => {
        console.warn("WebSocket error:", err);
        this.emitter.emit("error", err);
      };

      this.ws.onclose = () => {
        this.heartbeat.stop();
        this.ws = null;
        this.setStatus("disconnected");

        // Attempt automatic reconnection
        this.reconnector.scheduleReconnect(() => {
          this.setStatus("reconnecting");
          this.connect();
        });
      };
    } catch (err) {
      this.setStatus("error");
      console.error("Connection failed:", err);
    }
  }

  public disconnect(): void {
    this.reconnector.clear();
    this.heartbeat.stop();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setStatus("disconnected");
  }

  public sendFrame(frame: PtyFrame): void {
    if (this.status !== "connected" || !this.ws) {
      this.queue.enqueue(frame);
      return;
    }

    try {
      const raw = PtyProtocol.serialize(frame);
      this.ws.send(raw);
    } catch (err) {
      console.warn("Send failed, queuing frame:", err);
      this.queue.enqueue(frame);
    }
  }

  public sendText(text: string): void {
    this.sendFrame({ type: "text", payload: text });
  }

  public sendJson(data: any): void {
    this.sendFrame({ type: "json", payload: data });
  }

  public on(event: string, fn: (...args: any[]) => void): () => void {
    return this.emitter.on(event, fn);
  }

  public getStatus(): ConnectionStatus {
    return this.status;
  }

  public getLatencyStats(): LatencyStats {
    return this.heartbeat.getStats();
  }

  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    this.emitter.emit("status", status);
  }
}

export const ptyManager = PtyConnectionManager.getInstance();
