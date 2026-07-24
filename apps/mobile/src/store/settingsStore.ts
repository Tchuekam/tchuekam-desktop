import { create } from "zustand";

export interface SettingsState {
  telemetryOptOut: boolean;
  analyticsEnabled: boolean;
  autoConnectSocket: boolean;
  setTelemetryOptOut: (optOut: boolean) => void;
  setAutoConnectSocket: (autoConnect: boolean) => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  telemetryOptOut: false,
  analyticsEnabled: true,
  autoConnectSocket: true,

  setTelemetryOptOut: (telemetryOptOut) =>
    set({
      telemetryOptOut,
      analyticsEnabled: !telemetryOptOut,
    }),

  setAutoConnectSocket: (autoConnectSocket) => set({ autoConnectSocket }),
}));
