import { useState, useEffect, useCallback } from "react";
import { ptyManager } from "../lib/pty/connection";
import { ConnectionStatus, LatencyStats } from "../lib/pty/types";

export interface UsePtySocketReturn {
  connectionStatus: ConnectionStatus;
  isConnected: boolean;
  latency: LatencyStats;
  terminalOutput: string;
  connect: (sessionId?: string) => Promise<void>;
  disconnect: () => void;
  reconnect: () => void;
  send: (text: string) => void;
  sendJson: (data: any) => void;
  sendBinary: (data: ArrayBuffer) => void;
  clearTerminal: () => void;
}

export function usePtySocket(autoConnect = false): UsePtySocketReturn {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(ptyManager.getStatus());
  const [latency, setLatency] = useState<LatencyStats>(ptyManager.getLatencyStats());
  const [terminalOutput, setTerminalOutput] = useState<string>("");

  useEffect(() => {
    const unsubStatus = ptyManager.on("status", (newStatus: ConnectionStatus) => {
      setConnectionStatus(newStatus);
    });

    const unsubLatency = ptyManager.on("latency", (stats: LatencyStats) => {
      setLatency(stats);
    });

    const unsubOutput = ptyManager.on("output", (data: any) => {
      if (typeof data === "string") {
        setTerminalOutput((prev) => prev + data);
      }
    });

    if (autoConnect) {
      ptyManager.connect();
    }

    return () => {
      unsubStatus();
      unsubLatency();
      unsubOutput();
    };
  }, [autoConnect]);

  const connect = useCallback(async (sessionId?: string) => {
    await ptyManager.connect(sessionId);
  }, []);

  const disconnect = useCallback(() => {
    ptyManager.disconnect();
  }, []);

  const reconnect = useCallback(() => {
    ptyManager.disconnect();
    ptyManager.connect();
  }, []);

  const send = useCallback((text: string) => {
    ptyManager.sendText(text);
  }, []);

  const sendJson = useCallback((data: any) => {
    ptyManager.sendJson(data);
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    ptyManager.sendFrame({ type: "binary", payload: data });
  }, []);

  const clearTerminal = useCallback(() => {
    setTerminalOutput("");
  }, []);

  return {
    connectionStatus,
    isConnected: connectionStatus === "connected",
    latency,
    terminalOutput,
    connect,
    disconnect,
    reconnect,
    send,
    sendJson,
    sendBinary,
    clearTerminal,
  };
}
