/**
 * WebSocket PTY Engine — Types & Frame Definitions
 */

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "reconnecting" | "error";

export interface PtyFrame {
  type: "text" | "json" | "binary" | "ping" | "pong" | "resize" | "input";
  payload: any;
  timestamp?: number;
}

export interface PtyConnectionOptions {
  url?: string;
  token?: string;
  autoConnect?: boolean;
  heartbeatIntervalMs?: number;
  maxReconnectAttempts?: number;
}

export interface LatencyStats {
  currentMs: number;
  lastHeartbeat: string;
}
