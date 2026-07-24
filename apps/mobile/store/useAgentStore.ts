import { create } from "zustand";

export interface AgentState {
  sessionToken: string | null;
  currentSessionId: string | null;
  activeModel: string;
  telemetryOptOut: boolean;
  connectionStatus: "disconnected" | "connecting" | "connected";
  setSessionToken: (token: string | null) => void;
  setSessionId: (id: string | null) => void;
  setActiveModel: (model: string) => void;
  setTelemetryOptOut: (optOut: boolean) => void;
  setConnectionStatus: (status: "disconnected" | "connecting" | "connected") => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  sessionToken: null,
  currentSessionId: null,
  activeModel: "google/gemini-flash-1.5-8b",
  telemetryOptOut: false,
  connectionStatus: "disconnected",
  setSessionToken: (sessionToken) => set({ sessionToken }),
  setSessionId: (currentSessionId) => set({ currentSessionId }),
  setActiveModel: (activeModel) => set({ activeModel }),
  setTelemetryOptOut: (telemetryOptOut) => set({ telemetryOptOut }),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
}));
